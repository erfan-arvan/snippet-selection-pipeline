"""Stage C: candidate selection - filter the manifest down to methods passing a configurable
subset of the six §9.3 criteria (see `PipelineConfig.filtering.required_criteria`). No
redundancy/dedup pass yet (deferred per project decision until real candidate volume across
the 16 repos is visible).
"""
from __future__ import annotations

import json
from pathlib import Path

from .config import ALL_CRITERIA
from .method_analyzer import MethodRecord, load_manifest


def _passes_required_criteria(record: MethodRecord, required_criteria: list[str]) -> bool:
    """Recomputes pass/fail from the individual criteria fields already stored in the
    manifest, rather than trusting the record's precomputed `passesAllCriteria` (which always
    means "all six") - this is what lets which criteria matter be a config choice instead of
    requiring the manifest to be regenerated every time that choice changes.
    """
    criteria = record.raw.get("criteria", {})
    return all(criteria.get(name, False) for name in required_criteria)


def select_candidates(
    manifest_path: Path, candidates_path: Path, required_criteria: list[str] | None = None
) -> list[MethodRecord]:
    if required_criteria is None:
        required_criteria = ALL_CRITERIA

    records = load_manifest(manifest_path)
    candidates = [r for r in records if _passes_required_criteria(r, required_criteria)]

    candidates_path.parent.mkdir(parents=True, exist_ok=True)
    with open(candidates_path, "w") as f:
        for record in candidates:
            f.write(json.dumps(record.raw) + "\n")

    return candidates
