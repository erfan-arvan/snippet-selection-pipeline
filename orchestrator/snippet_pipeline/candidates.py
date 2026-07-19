"""Stage C: candidate selection - filter the manifest down to methods passing all six
§9.3 criteria. No redundancy/dedup pass yet (deferred per project decision until real
candidate volume across the 16 repos is visible).
"""
from __future__ import annotations

import json
from pathlib import Path

from .method_analyzer import MethodRecord, load_manifest


def select_candidates(manifest_path: Path, candidates_path: Path) -> list[MethodRecord]:
    records = load_manifest(manifest_path)
    candidates = [r for r in records if r.passes_all_criteria]

    candidates_path.parent.mkdir(parents=True, exist_ok=True)
    with open(candidates_path, "w") as f:
        for record in candidates:
            f.write(json.dumps(record.raw) + "\n")

    return candidates
