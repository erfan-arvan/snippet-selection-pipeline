#!/usr/bin/env python3
"""One-off analysis: list every distinct annotation name present in the legacy xlsx export's
Annotations column, with counts, so a whitelist of "acceptable" annotations can be decided
instead of the current blanket noAnnotations requirement.

The Annotations column holds a whitespace-separated list of plain annotation simple names -
confirmed against the real export (e.g. "Override  Nullable" for a method carrying both); no
leading "@", no brackets. The double space seen in practice is the old sanitizer turning ", "
into two spaces; `.split()` handles any run of whitespace regardless.

Usage:
    python3 list_annotations.py <input.xlsx>
"""
from __future__ import annotations

import sys
from collections import Counter

import openpyxl


def main(input_path: str) -> None:
    wb = openpyxl.load_workbook(input_path, read_only=True, data_only=True)
    ws = wb.active

    rows = ws.iter_rows(values_only=True)
    header = [str(h).strip() if h is not None else "" for h in next(rows)]
    method_idx = header.index("Method")
    annotations_idx = header.index("Annotations")

    total_rows = 0
    rows_with_annotations = 0
    name_counts: Counter[str] = Counter()
    raw_samples: list[str] = []

    for row in rows:
        if row is None:
            continue
        method_name = row[method_idx]
        if method_name is None or not str(method_name).strip():
            continue
        total_rows += 1

        raw = row[annotations_idx]
        raw = str(raw).strip() if raw is not None else ""
        if not raw:
            continue
        rows_with_annotations += 1

        if len(raw_samples) < 25:
            raw_samples.append(raw)

        name_counts.update(raw.split())

    print(f"Total methods: {total_rows}")
    print(f"Methods with a non-empty Annotations field: {rows_with_annotations}")
    print()
    print(f"--- First {len(raw_samples)} raw Annotations values (unparsed, for format sanity-check) ---")
    for s in raw_samples:
        print(repr(s))
    print()
    print(f"--- {len(name_counts)} distinct annotation names, by frequency ---")
    for name, count in name_counts.most_common():
        print(f"{count:>8}  {name}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <input.xlsx>", file=sys.stderr)
        sys.exit(1)
    main(sys.argv[1])
