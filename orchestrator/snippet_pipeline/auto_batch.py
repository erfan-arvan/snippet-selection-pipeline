"""Stage H: automatic batching driver.

Repeatedly samples a fresh, disjoint batch of up to `batch_size` methods from the already-
filtered `manifest/included.jsonl` pool (see candidates.write_included), runs each batch
through slice -> package -> check, and accumulates results across every batch run so far -
stopping once the cumulative checker findings satisfy the target counts, or the pool is
exhausted.

Unlike the per-stage CLI commands (`slice`/`package`/`check`, which each process a run's whole
`candidates.jsonl`/`snippets/` in one pass), this driver processes one batch's candidates at a
time and keeps its own cumulative results list - a batch's check stage never re-runs checkers
against a previous batch's already-packaged snippets, which would make each successive batch
more expensive than the last for no reason.

Classpath-resolved repos (the expensive part of staging - see classpath.resolve_classpath) are
cached in-memory for the whole driver run, not re-resolved per batch, since the same ~16 repos
are reused by every batch.

Progress is fully resumable: the shuffle order/offset and the cumulative results so far are
both persisted to disk after every batch, so a killed/timed-out run can just be restarted (same
command) and will continue from the last completed batch rather than starting over.
"""
from __future__ import annotations

import json
import random
from dataclasses import dataclass
from pathlib import Path

from . import checkers as checkers_stage
from . import packaging as packaging_stage
from . import specimin as specimin_stage
from . import stats as stats_stage
from .classpath import ResolvedRepo, stage_repo
from .config import PipelineConfig, RepoConfig
from .method_analyzer import MethodRecord, ensure_jar_built, load_manifest


def _state_path(run_dir: Path) -> Path:
    return run_dir / "manifest" / "auto_batch_state.json"


def _results_path(run_dir: Path) -> Path:
    return run_dir / "stats" / "auto_batch_results.jsonl"


def _load_state(run_dir: Path, seed: int) -> dict:
    path = _state_path(run_dir)
    if path.is_file():
        state = json.loads(path.read_text())
        if state.get("seed") != seed:
            raise RuntimeError(
                f"Existing state at {path} used seed={state.get('seed')}, but seed={seed} was "
                "given - the batch order would no longer match what's already been run. Pass "
                "the same seed to resume, or delete this file to start over from scratch."
            )
        return state
    return {"seed": seed, "next_offset": 0, "batches_run": 0}


def _save_state(run_dir: Path, state: dict) -> None:
    _state_path(run_dir).parent.mkdir(parents=True, exist_ok=True)
    _state_path(run_dir).write_text(json.dumps(state, indent=2))


def _load_cumulative_results(run_dir: Path) -> list[checkers_stage.CheckerRunResult]:
    path = _results_path(run_dir)
    if not path.is_file():
        return []
    results = []
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        d = json.loads(line)
        results.append(checkers_stage.CheckerRunResult(
            snippet_id=d["snippet_id"], checker_id=d["checker_id"], status=d["status"],
            on_target_count=d["on_target_count"], elsewhere_count=d["elsewhere_count"],
            diagnostics=[], log_path=Path(d["log_path"]), returncode=d["returncode"],
        ))
    return results


def _append_results(run_dir: Path, new_results: list[checkers_stage.CheckerRunResult]) -> None:
    path = _results_path(run_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a") as f:
        for r in new_results:
            f.write(json.dumps({
                "snippet_id": r.snippet_id, "checker_id": r.checker_id, "status": r.status,
                "on_target_count": r.on_target_count, "elsewhere_count": r.elsewhere_count,
                "returncode": r.returncode, "log_path": str(r.log_path),
            }) + "\n")


def _flagged_counts(results: list[checkers_stage.CheckerRunResult]) -> tuple[int, int]:
    flagged = [r for r in results if r.status == "flagged"]
    total = len(flagged)
    non_nullness = sum(1 for r in flagged if r.checker_id != "nullness")
    return total, non_nullness


def _get_resolved_repo(
    cache: dict[str, ResolvedRepo], repo: RepoConfig, staging_root: Path, gradle_cmd: str, maven_cmd: str
) -> ResolvedRepo:
    if repo.name not in cache:
        print(f"Resolving classpath for repo '{repo.name}' (first use this run - cached for all remaining batches)...", flush=True)
        cache[repo.name] = stage_repo(repo, staging_root, gradle_cmd, maven_cmd, resolve_jars=True)
    return cache[repo.name]


def _run_batch(
    config: PipelineConfig,
    run_dir: Path,
    batch: list[MethodRecord],
    repo_cache: dict[str, ResolvedRepo],
    batch_num: int,
) -> list[checkers_stage.CheckerRunResult]:
    staging_root = run_dir / "repos_staging"
    slices_root = run_dir / "slices"
    snippets_root = run_dir / "snippets"
    slice_logs_root = run_dir / "logs" / "slice"
    checker_logs_root = run_dir / "logs" / "checkers"

    jar_path = ensure_jar_built(config.tools)
    specimin_dir = Path(config.tools.specimin_dir).expanduser().resolve()
    method_analyzer_dir = Path(config.tools.method_analyzer_dir).expanduser().resolve()
    default_checker = config.checkers[0].processor if config.checkers else "org.checkerframework.checker.nullness.NullnessChecker"

    repo_by_name = {r.name: r for r in config.repos}

    sliced, packaged = 0, 0
    for i, record in enumerate(batch, 1):
        print(f"  [batch {batch_num}] slice+package {i}/{len(batch)}: {record.snippet_id} ...", flush=True)
        repo = repo_by_name.get(record.project)
        if repo is None:
            print(f"    SKIP: repo '{record.project}' not in config")
            continue
        resolved_repo = _get_resolved_repo(repo_cache, repo, staging_root, config.gradle_command, config.maven_command)

        try:
            source_root, target_file = specimin_stage.find_source_root_and_target_file(
                resolved_repo, resolved_repo.staging_dir, record
            )
        except specimin_stage.SourceRootNotFoundError as e:
            print(f"    SKIP: {e}")
            continue

        simple_class_name = record.qualified_class_name.rsplit(".", 1)[-1]
        try:
            qualified_class_name, param_types = specimin_stage.resolve_method_signature(
                jar_path, source_root / target_file, simple_class_name, record.method_name, record.num_params
            )
        except specimin_stage.SignatureResolutionError as e:
            print(f"    SKIP: could not resolve real signature - {e}")
            continue
        target_method_signature = f"{qualified_class_name}#{record.method_name}(" + ", ".join(param_types) + ")"

        slice_output_dir = slices_root / record.snippet_id
        slice_log_path = slice_logs_root / f"{record.snippet_id}.log"
        slice_result = specimin_stage.slice_candidate(
            specimin_dir, source_root, target_file, target_method_signature, slice_output_dir, slice_log_path
        )
        if not slice_result.success:
            print(f"    FAILED slice - see {slice_log_path}")
            continue
        sliced += 1

        try:
            packaging_stage.package_snippet(
                record, slice_output_dir, resolved_repo.classpath_jars,
                jar_path, method_analyzer_dir, snippets_root, config.checker_framework, default_checker,
            )
            packaged += 1
        except packaging_stage.PackagingError as e:
            print(f"    FAILED packaging - {e}")

    print(f"  [batch {batch_num}] sliced {sliced}/{len(batch)}, packaged {packaged}/{len(batch)}. Checking...", flush=True)

    batch_results = []
    for record in batch:
        snippet_dir = run_dir / "snippets" / record.snippet_id
        if not (snippet_dir / "snippet.json").is_file():
            continue
        batch_results.extend(checkers_stage.run_checkers_on_snippet(snippet_dir, config.checkers, checker_logs_root))

    return batch_results


def run_auto_batch(
    config: PipelineConfig,
    run_dir: Path,
    included_path: Path,
    batch_size: int = 1000,
    min_total_flagged: int = 100,
    min_non_nullness_flagged: int = 50,
    seed: int = 1,
) -> None:
    pool = load_manifest(included_path)
    random.Random(seed).shuffle(pool)
    print(f"Eligible pool: {len(pool)} methods (shuffled with seed={seed})")

    state = _load_state(run_dir, seed)
    cumulative = _load_cumulative_results(run_dir)
    repo_cache: dict[str, ResolvedRepo] = {}

    total_flagged, non_nullness_flagged = _flagged_counts(cumulative)
    print(f"Resuming from offset {state['next_offset']}/{len(pool)}, "
          f"{state['batches_run']} batch(es) already run, "
          f"{total_flagged} flagged so far ({non_nullness_flagged} non-nullness).")

    while True:
        if total_flagged >= min_total_flagged and non_nullness_flagged > min_non_nullness_flagged:
            print(f"\nStop condition met: {total_flagged} total flagged (>= {min_total_flagged}), "
                  f"{non_nullness_flagged} non-nullness flagged (> {min_non_nullness_flagged}).")
            break

        offset = state["next_offset"]
        if offset >= len(pool):
            print(f"\nPool exhausted ({len(pool)} methods) before stop condition was met: "
                  f"{total_flagged} total flagged, {non_nullness_flagged} non-nullness flagged.")
            break

        batch = pool[offset:offset + batch_size]
        batch_num = state["batches_run"] + 1
        print(f"\n=== Batch {batch_num}: methods {offset}-{offset + len(batch)} of {len(pool)} ===", flush=True)

        batch_results = _run_batch(config, run_dir, batch, repo_cache, batch_num)
        _append_results(run_dir, batch_results)
        cumulative.extend(batch_results)

        state["next_offset"] = offset + len(batch)
        state["batches_run"] = batch_num
        _save_state(run_dir, state)

        total_flagged, non_nullness_flagged = _flagged_counts(cumulative)
        batch_flagged, batch_non_nullness = _flagged_counts(batch_results)
        print(f"Batch {batch_num} done: {batch_flagged} flagged this batch ({batch_non_nullness} non-nullness). "
              f"Cumulative: {total_flagged} flagged ({non_nullness_flagged} non-nullness) "
              f"across {state['next_offset']} methods processed.", flush=True)

        stats_paths = stats_stage.write_stats(cumulative, run_dir / "stats")
        stats_stage.print_summary(cumulative, run_dir / "logs" / "checkers", stats_paths)
