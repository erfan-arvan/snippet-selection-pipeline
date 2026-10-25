#!/usr/bin/env python3
"""One-off analysis: list every distinct annotation name present in the legacy xlsx export's
Annotations column, with counts, so a whitelist of "acceptable" annotations can be decided
instead of the current blanket noAnnotations requirement.

The Annotations column is free text (possibly holding several annotations per method, in
whatever list-like format the old tool's sanitizeForCSV left it in) - rather than guess at and
depend on that exact format, this extracts every "@AnnotationName" substring via regex, which
is robust to however the individual annotations are separated/bracketed.

Usage:
    python3 list_annotations.py <input.xlsx>
"""
from __future__ import annotations

import re
import sys
from collections import Counter

import openpyxl

_ANNOTATION_NAME_RE = re.compile(r"@([A-Za-z_][A-Za-z0-9_.]*)")


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

        names = _ANNOTATION_NAME_RE.findall(raw)
        if names:
            name_counts.update(names)
        else:
            # Didn't match "@Name" at all - log the raw value itself so nothing is silently
            # dropped from the tally.
            name_counts[f"<unparsed: {raw[:60]!r}>"] += 1

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
