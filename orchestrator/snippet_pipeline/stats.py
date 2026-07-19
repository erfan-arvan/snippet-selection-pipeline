"""Stage G: aggregate Stage F's per-(snippet, checker) results into a stats table, persist it,
and print a console summary that always surfaces each result's log path - so a "flagged" or
"slice_suspect" row is traceable to its exact raw run without re-running anything.
"""
from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path

from .checkers import CheckerRunResult


def write_stats(results: list[CheckerRunResult], stats_dir: Path) -> tuple[Path, Path]:
    stats_dir.mkdir(parents=True, exist_ok=True)
    csv_path = stats_dir / "results.csv"
    jsonl_path = stats_dir / "results.jsonl"

    with open(csv_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["snippet_id", "checker_id", "status", "on_target_count", "elsewhere_count", "returncode", "log_path"])
        for r in results:
            writer.writerow([r.snippet_id, r.checker_id, r.status, r.on_target_count, r.elsewhere_count, r.returncode, str(r.log_path)])

    with open(jsonl_path, "w") as f:
        for r in results:
            f.write(json.dumps({
                "snippet_id": r.snippet_id,
                "checker_id": r.checker_id,
                "status": r.status,
                "on_target_count": r.on_target_count,
                "elsewhere_count": r.elsewhere_count,
                "returncode": r.returncode,
                "log_path": str(r.log_path),
                "diagnostics": [d.__dict__ for d in r.diagnostics],
            }) + "\n")

    return csv_path, jsonl_path


def print_summary(results: list[CheckerRunResult], logs_root: Path, stats_paths: tuple[Path, Path]) -> str:
    lines = []
    lines.append(f"Run log directory: {logs_root}")
    lines.append(f"Stats CSV:  {stats_paths[0]}")
    lines.append(f"Stats JSONL: {stats_paths[1]}")
    lines.append("")

    by_checker: dict[str, Counter] = {}
    for r in results:
        by_checker.setdefault(r.checker_id, Counter())[r.status] += 1

    lines.append(f"{'checker':<15} {'passed':>8} {'flagged':>8} {'slice_suspect':>14} {'run_error':>10}")
    for checker_id, counts in sorted(by_checker.items()):
        lines.append(
            f"{checker_id:<15} {counts.get('passed', 0):>8} {counts.get('flagged', 0):>8} "
            f"{counts.get('slice_suspect', 0):>14} {counts.get('run_error', 0):>10}"
        )

    lines.append("")
    lines.append("Rows needing manual triage (flagged) or slice review (slice_suspect):")
    for r in results:
        if r.status in ("flagged", "slice_suspect"):
            lines.append(f"  [{r.status}] {r.snippet_id} / {r.checker_id} -> log: {r.log_path}")

    summary = "\n".join(lines)
    print(summary)
    return summary
