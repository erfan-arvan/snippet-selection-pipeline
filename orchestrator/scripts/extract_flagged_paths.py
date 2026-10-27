#!/usr/bin/env python3
"""Joins a run's flagged/slice_suspect/slice_broken checker results (stats/auto_batch_results.jsonl
or stats/results.jsonl) against each snippet's packaged metadata.json (snippets/<snippet_id>/metadata.json)
to answer "where in the real source is this warning" - the results files alone only carry snippet_id and
a checker log path, not the original file/line location.

Usage:
    python3 extract_flagged_paths.py <run_dir> [output.csv]

<run_dir> is the run's output directory, e.g.
/project/mjk76/ea442/snippet-selection-pipeline-output/legacy-import - it's expected to contain
stats/auto_batch_results.jsonl (falls back to stats/results.jsonl) and snippets/<snippet_id>/metadata.json.
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path


def main(run_dir: str, out_path: str) -> None:
    run_dir_path = Path(run_dir)
    results_path = run_dir_path / "stats" / "auto_batch_results.jsonl"
    if not results_path.is_file():
        results_path = run_dir_path / "stats" / "results.jsonl"

    rows = []
    seen = set()
    with open(results_path) as f:
        for line in f:
            r = json.loads(line)
            if r["status"] not in ("flagged", "slice_suspect", "slice_broken"):
                continue
            key = (r["snippet_id"], r["checker_id"])
            if key in seen:
                continue
            seen.add(key)

            metadata_path = run_dir_path / "snippets" / r["snippet_id"] / "metadata.json"
            if not metadata_path.is_file():
                print(f"WARNING: no metadata.json for {r['snippet_id']} (expected at {metadata_path})",
                      file=sys.stderr)
                continue
            m = json.loads(metadata_path.read_text())

            rows.append({
                "snippet_id": r["snippet_id"],
                "checker_id": r["checker_id"],
                "status": r["status"],
                "repo": m["repo"],
                "original_file": m["original_file"],
                "original_start_line": m["original_start_line"],
                "original_end_line": m["original_end_line"],
                "qualified_class_name": m["qualified_class_name"],
                "method_name": m["method_name"],
                "log_path": r["log_path"],
            })

    with open(out_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()) if rows else [
            "snippet_id", "checker_id", "status", "repo", "original_file",
            "original_start_line", "original_end_line", "qualified_class_name", "method_name", "log_path",
        ])
        writer.writeheader()
        writer.writerows(rows)

    print(f"{len(rows)} flagged/suspect/broken (snippet, checker) row(s) -> {out_path}")


if __name__ == "__main__":
    if len(sys.argv) not in (2, 3):
        print(f"Usage: {sys.argv[0]} <run_dir> [output.csv]", file=sys.stderr)
        sys.exit(1)
    run_dir_arg = sys.argv[1]
    out_arg = sys.argv[2] if len(sys.argv) == 3 else "flagged_paths.csv"
    main(run_dir_arg, out_arg)
