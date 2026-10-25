"""CLI entrypoint. Each stage can be run independently (useful when iterating/debugging one
stage against already-produced output from a previous stage) or chained via `all`.

Run identity: `filter` is the pipeline's entry stage - it mints a run id (or uses one you
pass via --run-id / set in pipeline.yaml) and records it as "the most recent run". Every
later stage is a separate process that reloads the config from scratch, so they resolve the
same run by reading that record back, unless you pass --run-id explicitly to target a
specific historical run.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import auto_batch as auto_batch_stage
from . import candidates as candidates_stage
from . import checkers as checkers_stage
from . import method_analyzer
from . import packaging as packaging_stage
from . import specimin as specimin_stage
from . import stats as stats_stage
from .classpath import stage_all_repos
from .config import PipelineConfig, load_config


def _load_config_with_run_id_override(args) -> PipelineConfig:
    config = load_config(args.config)
    if getattr(args, "run_id", None):
        config.run_id = args.run_id
    return config


def repos_needed_by(candidates, all_repos):
    """Filters `all_repos` down to only those referenced by at least one of `candidates`.

    Used before staging/classpath-resolving repos for slice/package: a repo with zero
    candidates in the current run has no work to do, regardless of what criteria produced
    that candidate set - this holds for any candidate set, not just today's.
    """
    needed_names = {record.project for record in candidates}
    return [r for r in all_repos if r.name in needed_names]


def cmd_stage_and_filter(args) -> None:
    config = _load_config_with_run_id_override(args)
    run_id = config.start_new_run()
    run_dir = config.run_output_dir(run_id)
    staging_root = run_dir / "repos_staging"

    print(f"Run id: {run_id}")
    print(f"Staging {len(config.repos)} repo(s) into {staging_root} ...")
    resolved_repos = stage_all_repos(config.repos, staging_root, config.gradle_command, config.maven_command)
    for rr in resolved_repos:
        print(f"  {rr.repo.name}: {len(rr.source_roots)} source root(s), {len(rr.classpath_jars)} classpath jar(s)")

    jar_path = method_analyzer.ensure_jar_built(config.tools)
    manifest_path = run_dir / "manifest" / "manifest.jsonl"
    log_path = run_dir / "logs" / "method_analyzer.log"
    print(f"Running MethodAnalyzerApp -> {manifest_path}")
    method_analyzer.run_method_analyzer(jar_path, staging_root, manifest_path, log_path)
    print(f"Manifest written to {manifest_path} (full run log: {log_path})")


def cmd_select(args) -> None:
    config = _load_config_with_run_id_override(args)
    run_dir = config.run_output_dir(config.resolve_existing_run_id())
    manifest_path = run_dir / "manifest" / "manifest.jsonl"
    included_path = run_dir / "manifest" / "included.jsonl"
    candidates_path = run_dir / "manifest" / "candidates.jsonl"

    required = config.filtering.required_criteria
    if args.resample_only:
        # Re-sample from the already-filtered pool without re-scanning the (potentially huge)
        # manifest - use this when only --limit/--seed changed, not the required criteria.
        if not included_path.is_file():
            raise RuntimeError(
                f"--resample-only given but {included_path} doesn't exist yet - run `select` "
                "at least once without it first."
            )
        print(f"Resampling from existing {included_path} (not re-filtering the manifest)")
    else:
        included = candidates_stage.write_included(manifest_path, included_path, required)
        print(f"{len(included)} method(s) passing required criteria {required} -> {included_path}")

    candidates = candidates_stage.sample_candidates(included_path, candidates_path, limit=args.limit, seed=args.seed)
    limit_note = f" (limit={args.limit}, seed={args.seed}; randomly sampled if the pool was larger)" if args.limit else ""
    print(f"{len(candidates)} candidate(s) selected{limit_note} -> {candidates_path}")


def cmd_slice(args) -> None:
    from .method_analyzer import load_manifest

    config = _load_config_with_run_id_override(args)
    run_dir = config.run_output_dir(config.resolve_existing_run_id())
    staging_root = run_dir / "repos_staging"
    candidates_path = run_dir / "manifest" / "candidates.jsonl"
    slices_root = run_dir / "slices"
    logs_root = run_dir / "logs" / "slice"

    candidates = load_manifest(candidates_path)
    repos_to_stage = repos_needed_by(candidates, config.repos)
    print(f"Staging {len(repos_to_stage)} of {len(config.repos)} configured repo(s) - only those with candidates in this run.")

    resolved_repos = {
        rr.repo.name: rr
        for rr in stage_all_repos(
            repos_to_stage, staging_root, config.gradle_command, config.maven_command, resolve_jars=False
        )
    }
    specimin_dir = Path(config.tools.specimin_dir).expanduser().resolve()
    jar_path = method_analyzer.ensure_jar_built(config.tools)

    succeeded, failed = 0, 0
    for i, record in enumerate(candidates, 1):
        print(f"Slicing candidate {i}/{len(candidates)}: {record.snippet_id} ...", flush=True)
        resolved_repo = resolved_repos.get(record.project)
        if resolved_repo is None:
            print(f"  SKIP {record.snippet_id}: repo '{record.project}' not staged")
            failed += 1
            continue

        try:
            source_root, target_file = specimin_stage.find_source_root_and_target_file(
                resolved_repo, resolved_repo.staging_dir, record
            )
        except specimin_stage.SourceRootNotFoundError as e:
            print(f"  SKIP {record.snippet_id}: {e}")
            failed += 1
            continue

        # Never trust the manifest's own qualifiedClassName/targetMethodSignature for slicing -
        # re-derive it from the actual source file (as-written types, correct nested-class
        # chain) since manifest values imported from the legacy xlsx can be wrong in ways that
        # produce an unusable --targetMethod (see specimin.resolve_method_signature).
        simple_class_name = record.qualified_class_name.rsplit(".", 1)[-1]
        try:
            qualified_class_name, param_types = specimin_stage.resolve_method_signature(
                jar_path, source_root / target_file, simple_class_name, record.method_name, record.num_params
            )
        except specimin_stage.SignatureResolutionError as e:
            print(f"  SKIP {record.snippet_id}: could not resolve real signature from source - {e}")
            failed += 1
            continue
        target_method_signature = f"{qualified_class_name}#{record.method_name}(" + ", ".join(param_types) + ")"

        output_dir = slices_root / record.snippet_id
        log_path = logs_root / f"{record.snippet_id}.log"
        result = specimin_stage.slice_candidate(
            specimin_dir, source_root, target_file,
            target_method_signature, output_dir, log_path,
        )
        if result.success:
            succeeded += 1
        else:
            failed += 1
            print(f"  FAILED slice for {record.snippet_id} - see {log_path}")

    print(f"Slicing done: {succeeded} succeeded, {failed} failed. Logs under {logs_root}")


def cmd_package(args) -> None:
    from .method_analyzer import load_manifest

    config = _load_config_with_run_id_override(args)
    run_dir = config.run_output_dir(config.resolve_existing_run_id())
    staging_root = run_dir / "repos_staging"
    candidates_path = run_dir / "manifest" / "candidates.jsonl"
    slices_root = run_dir / "slices"
    snippets_root = run_dir / "snippets"

    candidates = load_manifest(candidates_path)
    repos_to_stage = repos_needed_by(candidates, config.repos)

    resolved_repos = {rr.repo.name: rr for rr in stage_all_repos(repos_to_stage, staging_root, config.gradle_command, config.maven_command)}
    jar_path = config.tools.resolved_jar()
    method_analyzer_dir = Path(config.tools.method_analyzer_dir).expanduser().resolve()
    default_checker = config.checkers[0].processor if config.checkers else "org.checkerframework.checker.nullness.NullnessChecker"

    succeeded, failed = 0, 0
    for record in candidates:
        slice_output_dir = slices_root / record.snippet_id
        if not slice_output_dir.is_dir() or not any(slice_output_dir.rglob("*.java")):
            continue  # slicing didn't succeed for this candidate; nothing to package

        resolved_repo = resolved_repos.get(record.project)
        try:
            packaging_stage.package_snippet(
                record, slice_output_dir, resolved_repo.classpath_jars if resolved_repo else [],
                jar_path, method_analyzer_dir, snippets_root, config.checker_framework, default_checker,
            )
            succeeded += 1
        except packaging_stage.PackagingError as e:
            print(f"  FAILED packaging {record.snippet_id}: {e}")
            failed += 1

    print(f"Packaging done: {succeeded} succeeded, {failed} failed. Snippets under {snippets_root}")


def cmd_check(args) -> None:
    config = _load_config_with_run_id_override(args)
    run_dir = config.run_output_dir(config.resolve_existing_run_id())
    snippets_root = run_dir / "snippets"
    logs_root = run_dir / "logs" / "checkers"
    stats_dir = run_dir / "stats"

    all_results = []
    for snippet_dir in sorted(p for p in snippets_root.iterdir() if p.is_dir()):
        if not (snippet_dir / "snippet.json").is_file():
            continue
        all_results.extend(
            checkers_stage.run_checkers_on_snippet(snippet_dir, config.checkers, logs_root)
        )

    stats_paths = stats_stage.write_stats(all_results, stats_dir)
    stats_stage.print_summary(all_results, logs_root, stats_paths)


def cmd_all(args) -> None:
    cmd_stage_and_filter(args)
    cmd_select(args)
    cmd_slice(args)
    cmd_package(args)
    cmd_check(args)


def cmd_auto(args) -> None:
    config = _load_config_with_run_id_override(args)
    run_dir = config.run_output_dir(config.resolve_existing_run_id())
    included_path = run_dir / "manifest" / "included.jsonl"
    if not included_path.is_file():
        raise RuntimeError(
            f"{included_path} doesn't exist - run `select` at least once first (it writes "
            "the eligible pool this stage samples batches from)."
        )
    auto_batch_stage.run_auto_batch(
        config, run_dir, included_path,
        batch_size=args.batch_size,
        min_total_flagged=args.min_total_flagged,
        min_non_nullness_flagged=args.min_non_nullness_flagged,
        seed=args.auto_seed,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="snippet-pipeline")
    parser.add_argument("-c", "--config", default="config/pipeline.yaml", help="Path to pipeline.yaml")
    parser.add_argument(
        "--run-id", default=None,
        help="Target a specific run directory instead of the most recently started one "
             "(required if you're running stages from different processes/machines without "
             "a shared output_dir, or want to re-run a stage against an older run).",
    )
    parser.add_argument(
        "--limit", type=int, default=None,
        help="select stage only: cap the candidate set to this many, chosen at random (not "
             "the first N, since candidates.jsonl's ordering isn't representative) - useful "
             "for a quick sanity-check run of slice/package/check before committing to the "
             "full candidate set.",
    )
    parser.add_argument(
        "--seed", type=int, default=None,
        help="select stage only: random seed for --limit, for a reproducible sample.",
    )
    parser.add_argument(
        "--resample-only", action="store_true",
        help="select stage only: skip re-filtering the manifest (which can have hundreds of "
             "thousands of rows) and just draw a new --limit/--seed sample from the existing "
             "manifest/included.jsonl pool. Use this when only the sample size/seed changed, "
             "not the required criteria - omit it (or change required_criteria first) to "
             "regenerate included.jsonl from the manifest.",
    )
    parser.add_argument(
        "--batch-size", type=int, default=1000,
        help="auto stage only: how many eligible methods to pull per batch.",
    )
    parser.add_argument(
        "--min-total-flagged", type=int, default=100,
        help="auto stage only: stop once cumulative flagged findings (across all checkers) "
             "reach at least this many.",
    )
    parser.add_argument(
        "--min-non-nullness-flagged", type=int, default=50,
        help="auto stage only: stop once cumulative flagged findings from checkers other than "
             "nullness exceed this many (both this and --min-total-flagged must hold).",
    )
    parser.add_argument(
        "--auto-seed", type=int, default=1,
        help="auto stage only: seed for shuffling the eligible pool into batches. Keep this "
             "the same across resumed runs - changing it is rejected (see auto_batch_state.json).",
    )
    subparsers = parser.add_subparsers(dest="stage", required=True)

    subparsers.add_parser("filter", help="Stage A+B: resolve classpaths, stage repos, run MethodAnalyzerApp").set_defaults(func=cmd_stage_and_filter)
    subparsers.add_parser("select", help="Stage C: select candidates passing the configured required criteria").set_defaults(func=cmd_select)
    subparsers.add_parser("slice", help="Stage D: slice each candidate with Specimin").set_defaults(func=cmd_slice)
    subparsers.add_parser("package", help="Stage E: package each slice as a standalone Gradle module").set_defaults(func=cmd_package)
    subparsers.add_parser("check", help="Stage F+G: run Checker Framework checkers and print stats").set_defaults(func=cmd_check)
    subparsers.add_parser("all", help="Run every stage in sequence").set_defaults(func=cmd_all)
    subparsers.add_parser(
        "auto",
        help="Stage H: repeatedly batch-sample from manifest/included.jsonl, running slice/"
             "package/check on each batch, until cumulative flagged findings hit the target "
             "counts (or the pool runs out). Resumable - re-run the same command to continue "
             "after a timeout/interruption.",
    ).set_defaults(func=cmd_auto)

    args = parser.parse_args(argv)
    args.func(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
