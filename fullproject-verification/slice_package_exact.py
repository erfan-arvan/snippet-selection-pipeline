#!/usr/bin/env python3
"""Slice + package for the original-warnings runs, using the EXACT method that holds the warning.

Same steps and the same pipeline functions as `snippet_pipeline.cli slice` and `package` (the
pipeline itself is not changed), with three differences for this part of the work:
  * overloads: the method is the one mine_original_warnings.py found around the warning
    (fpvClass / fpvEndLine / fpvParamTypes in candidates.jsonl), so an overloaded method is sliced
    instead of being skipped as "ambiguous", and every overload has its own snippet id (fpvSnippetId);
  * inside the slice the method is located by its parameter types, not just the first one with
    that name and number of parameters;
  * a Specimin timeout fails only that method; the run goes on.
Records without the fpv fields are handled exactly like the pipeline does.

usage: slice_package_exact.py -c CONFIG --run-id RUN_ID
"""
import argparse, json, subprocess, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "orchestrator"))
from snippet_pipeline import method_analyzer, packaging as packaging_stage, specimin as specimin_stage  # noqa: E402
from snippet_pipeline.classpath import stage_all_repos  # noqa: E402
from snippet_pipeline.cli import repos_needed_by  # noqa: E402
from snippet_pipeline.config import load_config  # noqa: E402
from snippet_pipeline.method_analyzer import MethodRecord, load_manifest  # noqa: E402

RESOLVER = str(HERE / "ResolveExact.java")


class ExactRecord(MethodRecord):
    @property
    def snippet_id(self) -> str:
        return self.raw.get("fpvSnippetId") or super().snippet_id


def run_resolver(jar, *args):
    p = subprocess.run(["java", "-cp", str(jar), RESOLVER, *map(str, args)], capture_output=True, text=True, timeout=120)
    if p.returncode != 0:
        raise RuntimeError(p.stderr.strip().splitlines()[-1] if p.stderr.strip() else f"exit {p.returncode}")
    return p.stdout.strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-c", "--config", required=True)
    ap.add_argument("--run-id", required=True)
    a = ap.parse_args()
    config = load_config(a.config)
    config.run_id = a.run_id
    run_dir = config.run_output_dir(config.resolve_existing_run_id())
    candidates = [ExactRecord(r.raw) for r in load_manifest(run_dir / "manifest" / "candidates.jsonl")]
    slices_root, snippets_root = run_dir / "slices", run_dir / "snippets"
    logs_root = run_dir / "logs" / "slice"
    repos = repos_needed_by(candidates, config.repos)
    jar = method_analyzer.ensure_jar_built(config.tools)

    # ---- slice (as cli.cmd_slice) ----
    print(f"Staging {len(repos)} repo(s).", flush=True)
    resolved = {rr.repo.name: rr for rr in stage_all_repos(repos, run_dir / "repos_staging", config.gradle_command,
                                                           config.maven_command, resolve_jars=False)}
    specimin_dir = Path(config.tools.specimin_dir).expanduser().resolve()
    ok = failed = 0
    for i, rec in enumerate(candidates, 1):
        sid = rec.snippet_id
        print(f"Slicing candidate {i}/{len(candidates)}: {sid} ...", flush=True)
        rr = resolved.get(rec.project)
        if rr is None:
            print(f"  SKIP {sid}: repo '{rec.project}' not staged"); failed += 1; continue
        try:
            source_root, target_file = specimin_stage.find_source_root_and_target_file(rr, rr.staging_dir, rec)
        except specimin_stage.SourceRootNotFoundError as e:
            print(f"  SKIP {sid}: {e}"); failed += 1; continue
        try:
            if "fpvEndLine" in rec.raw:
                simple = rec.raw["fpvClass"].rsplit(".", 1)[-1]
                out = run_resolver(jar, "resolve", source_root / target_file, simple, rec.method_name, rec.num_params,
                                   rec.raw["fpvEndLine"])
                d = json.loads(out)
                qcls, ptypes = d["qualifiedClassName"], d["paramTypes"]
            else:
                qcls, ptypes = specimin_stage.resolve_method_signature(
                    jar, source_root / target_file, rec.qualified_class_name.rsplit(".", 1)[-1], rec.method_name, rec.num_params)
        except (RuntimeError, specimin_stage.SignatureResolutionError) as e:
            print(f"  SKIP {sid}: could not resolve real signature from source - {e}"); failed += 1; continue
        rec.raw["fpvResolvedParamTypes"] = ptypes          # used to find the same overload inside the slice
        signature = f"{qcls}#{rec.method_name}(" + ", ".join(ptypes) + ")"
        out_dir, log_path = slices_root / sid, logs_root / f"{sid}.log"
        try:
            res = specimin_stage.slice_candidate(specimin_dir, source_root, target_file, signature, out_dir, log_path)
            good = res.success
        except subprocess.TimeoutExpired:
            log_path.parent.mkdir(parents=True, exist_ok=True)
            log_path.write_text(f"TIMEOUT: Specimin did not finish within the pipeline's time limit\nsignature: {signature}\n")
            good = False
        if good:
            ok += 1
        else:
            failed += 1
            print(f"  FAILED slice for {sid} - see {log_path}")
    print(f"Slicing done: {ok} succeeded, {failed} failed. Logs under {logs_root}", flush=True)

    # ---- package (as cli.cmd_package), locating the exact overload inside the slice ----
    resolved = {rr.repo.name: rr for rr in stage_all_repos(repos, run_dir / "repos_staging", config.gradle_command,
                                                           config.maven_command)}
    current = {}
    original_locate = packaging_stage.locate_method_in_slice

    def exact_locate(jar_path, sliced_file, method_name, num_params):
        types = current.get("types")
        if not types:
            return original_locate(jar_path, sliced_file, method_name, num_params)
        try:
            b, e = run_resolver(jar_path, "locate", sliced_file, method_name, num_params, *types).split(",")
            return int(b), int(e)
        except RuntimeError as err:
            raise packaging_stage.PackagingError(f"Could not locate {method_name}{types} in {sliced_file}: {err}")

    packaging_stage.locate_method_in_slice = exact_locate      # only inside this process
    default_checker = config.checkers[0].processor if config.checkers else "org.checkerframework.checker.nullness.NullnessChecker"
    ma_dir = Path(config.tools.method_analyzer_dir).expanduser().resolve()
    ok = failed = 0
    for rec in candidates:
        sdir = slices_root / rec.snippet_id
        if not sdir.is_dir() or not any(sdir.rglob("*.java")):
            continue
        current["types"] = rec.raw.get("fpvResolvedParamTypes") if "fpvEndLine" in rec.raw else None
        rr = resolved.get(rec.project)
        try:
            packaging_stage.package_snippet(rec, sdir, rr.classpath_jars if rr else [], jar, ma_dir, snippets_root,
                                            config.checker_framework, default_checker)
            ok += 1
        except packaging_stage.PackagingError as e:
            print(f"  FAILED packaging {rec.snippet_id}: {e}")
            failed += 1
    print(f"Packaging done: {ok} succeeded, {failed} failed. Snippets under {snippets_root}", flush=True)


if __name__ == "__main__":
    main()
