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
    candidates_path = run_dir / "manifest" / "candidates.jsonl"

    candidates = candidates_stage.select_candidates(manifest_path, candidates_path)
    print(f"{len(candidates)} candidate(s) passing all six criteria -> {candidates_path}")


def cmd_slice(args) -> None:
    from .method_analyzer import load_manifest

    config = _load_config_with_run_id_override(args)
    run_dir = config.run_output_dir(config.resolve_existing_run_id())
    staging_root = run_dir / "repos_staging"
    candidates_path = run_dir / "manifest" / "candidates.jsonl"
    slices_root = run_dir / "slices"
    logs_root = run_dir / "logs" / "slice"

    resolved_repos = {rr.repo.name: rr for rr in stage_all_repos(config.repos, staging_root, config.gradle_command, config.maven_command)}
    specimin_dir = Path(config.tools.specimin_dir).expanduser().resolve()

    jar_dirs: dict[str, Path] = {}
    succeeded, failed = 0, 0
    for record in load_manifest(candidates_path):
        resolved_repo = resolved_repos.get(record.project)
        if resolved_repo is None:
            print(f"  SKIP {record.snippet_id}: repo '{record.project}' not staged")
            failed += 1
            continue

        if record.project not in jar_dirs:
            jar_dirs[record.project] = specimin_stage.materialize_jar_dir(
                resolved_repo, run_dir / "jar_dirs" / record.project
            )

        try:
            source_root, target_file = specimin_stage.find_source_root_and_target_file(
                resolved_repo, resolved_repo.staging_dir, record
            )
        except specimin_stage.SourceRootNotFoundError as e:
            print(f"  SKIP {record.snippet_id}: {e}")
            failed += 1
            continue

        output_dir = slices_root / record.snippet_id
        log_path = logs_root / f"{record.snippet_id}.log"
        result = specimin_stage.slice_candidate(
            specimin_dir, source_root, target_file,
            record.target_method_signature, jar_dirs[record.project], output_dir, log_path,
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

    resolved_repos = {rr.repo.name: rr for rr in stage_all_repos(config.repos, staging_root, config.gradle_command, config.maven_command)}
    jar_path = config.tools.resolved_jar()
    method_analyzer_dir = Path(config.tools.method_analyzer_dir).expanduser().resolve()
    default_checker = config.checkers[0].processor if config.checkers else "org.checkerframework.checker.nullness.NullnessChecker"

    succeeded, failed = 0, 0
    for record in load_manifest(candidates_path):
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="snippet-pipeline")
    parser.add_argument("-c", "--config", default="config/pipeline.yaml", help="Path to pipeline.yaml")
    parser.add_argument(
        "--run-id", default=None,
        help="Target a specific run directory instead of the most recently started one "
             "(required if you're running stages from different processes/machines without "
             "a shared output_dir, or want to re-run a stage against an older run).",
    )
    subparsers = parser.add_subparsers(dest="stage", required=True)

    subparsers.add_parser("filter", help="Stage A+B: resolve classpaths, stage repos, run MethodAnalyzerApp").set_defaults(func=cmd_stage_and_filter)
    subparsers.add_parser("select", help="Stage C: select candidates passing all six criteria").set_defaults(func=cmd_select)
    subparsers.add_parser("slice", help="Stage D: slice each candidate with Specimin").set_defaults(func=cmd_slice)
    subparsers.add_parser("package", help="Stage E: package each slice as a standalone Gradle module").set_defaults(func=cmd_package)
    subparsers.add_parser("check", help="Stage F+G: run Checker Framework checkers and print stats").set_defaults(func=cmd_check)
    subparsers.add_parser("all", help="Run every stage in sequence").set_defaults(func=cmd_all)

    args = parser.parse_args(argv)
    args.func(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
