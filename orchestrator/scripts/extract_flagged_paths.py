#!/usr/bin/env python3
"""Joins a run's checker results (stats/results.jsonl, which carries each diagnostic's actual
Checker Framework message - stats/auto_batch_results.jsonl does NOT, it's checker-agnostic) against
each snippet's packaged metadata (snippets/<snippet_id>/snippet.json) to answer "where in the real
source is this warning, and what did the checker actually say" in one row per diagnostic.

Usage:
    python3 extract_flagged_paths.py <run_dir> [output.csv]

<run_dir> is the run's output directory, e.g.
/project/mjk76/ea442/snippet-selection-pipeline-output/legacy-import - it's expected to contain
stats/results.jsonl and snippets/<snippet_id>/snippet.json.
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

FIELDNAMES = [
    "snippet_id", "checker_id", "status", "repo", "original_file",
    "original_start_line", "original_end_line", "qualified_class_name", "method_name",
    "on_target", "severity", "key", "message", "diagnostic_line", "log_path",
]


def main(run_dir: str, out_path: str) -> None:
    run_dir_path = Path(run_dir)
    results_path = run_dir_path / "stats" / "results.jsonl"
    if not results_path.is_file():
        sys.exit(f"{results_path} not found - run the pipeline's `check` stage (or `auto`) first "
                  "so stats/results.jsonl exists; auto_batch_results.jsonl alone has no diagnostic messages.")

    rows = []
    metadata_cache: dict[str, dict | None] = {}

    def load_metadata(snippet_id: str) -> dict | None:
        if snippet_id not in metadata_cache:
            metadata_path = run_dir_path / "snippets" / snippet_id / "snippet.json"
            if metadata_path.is_file():
                metadata_cache[snippet_id] = json.loads(metadata_path.read_text())
            else:
                print(f"WARNING: no snippet.json for {snippet_id} (expected at {metadata_path})", file=sys.stderr)
                metadata_cache[snippet_id] = None
        return metadata_cache[snippet_id]

    with open(results_path) as f:
        for line in f:
            r = json.loads(line)
            if r["status"] not in ("flagged", "slice_suspect", "slice_broken"):
                continue

            m = load_metadata(r["snippet_id"])
            base = {
                "snippet_id": r["snippet_id"],
                "checker_id": r["checker_id"],
                "status": r["status"],
                "repo": m["repo"] if m else None,
                "original_file": m["original_file"] if m else None,
                "original_start_line": m["original_start_line"] if m else None,
                "original_end_line": m["original_end_line"] if m else None,
                "qualified_class_name": m["qualified_class_name"] if m else None,
                "method_name": m["method_name"] if m else None,
                "log_path": r["log_path"],
            }

            diagnostics = r.get("diagnostics") or []
            if not diagnostics:
                # slice_broken rows can have zero parsed diagnostics (e.g. run_error) - still
                # worth a row so the snippet isn't silently dropped from the CSV.
                rows.append({**base, "on_target": None, "severity": None, "key": None,
                             "message": None, "diagnostic_line": None})
                continue
            for d in diagnostics:
                rows.append({**base, "on_target": d["on_target"], "severity": d["severity"],
                             "key": d["key"], "message": d["message"], "diagnostic_line": d["line"]})

    with open(out_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)

    print(f"{len(rows)} diagnostic row(s) -> {out_path}")


if __name__ == "__main__":
    if len(sys.argv) not in (2, 3):
        print(f"Usage: {sys.argv[0]} <run_dir> [output.csv]", file=sys.stderr)
        sys.exit(1)
    run_dir_arg = sys.argv[1]
    out_arg = sys.argv[2] if len(sys.argv) == 3 else "flagged_paths.csv"
    main(run_dir_arg, out_arg)
