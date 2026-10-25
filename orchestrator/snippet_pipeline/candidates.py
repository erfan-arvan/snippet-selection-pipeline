"""Stage C: candidate selection - filter the manifest down to methods passing a configurable
subset of the six §9.3 criteria (see `PipelineConfig.filtering.required_criteria`). No
redundancy/dedup pass yet (deferred per project decision until real candidate volume across
the 16 repos is visible).

Split into two steps so that re-sampling a different N (or re-running downstream stages)
never has to re-scan the full manifest:
  1. `write_included` filters the manifest (potentially hundreds of thousands of rows) down to
     every method passing the required criteria, and persists that full pool to its own file
     (`included.jsonl`) - this is the expensive step, and only needs re-running when the
     manifest or the required criteria change.
  2. `sample_candidates` draws a (possibly random, possibly capped) sample from that already-
     filtered, persisted pool into `candidates.jsonl` - cheap, and safe to re-run repeatedly
     (e.g. to try a different --limit/--seed) without touching the manifest at all.
`select_candidates` remains as a convenience wrapper that does both in one call.
"""
from __future__ import annotations

import json
import random
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


def _write_records(path: Path, records: list[MethodRecord]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        for record in records:
            f.write(json.dumps(record.raw) + "\n")


def write_included(
    manifest_path: Path,
    included_path: Path,
    required_criteria: list[str] | None = None,
) -> list[MethodRecord]:
    """Filters the full manifest down to every method passing `required_criteria` (no
    sampling/limit) and persists that pool to `included_path`. This is the single source of
    truth for "what currently qualifies" - re-run it whenever the manifest or the required
    criteria change, then sample from its output rather than from the manifest directly.
    """
    if required_criteria is None:
        required_criteria = ALL_CRITERIA

    records = load_manifest(manifest_path)
    included = [r for r in records if _passes_required_criteria(r, required_criteria)]
    _write_records(included_path, included)
    return included


def sample_candidates(
    included_path: Path,
    candidates_path: Path,
    limit: int | None = None,
    seed: int | None = None,
) -> list[MethodRecord]:
    """Draws a sample from the already-filtered `included_path` pool into `candidates_path` -
    never re-reads or re-filters the manifest, so this is cheap and safe to re-run with a
    different limit/seed at any time.
    """
    candidates = load_manifest(included_path)

    if limit is not None and len(candidates) > limit:
        # Random, not "first N": the included pool's ordering reflects wherever the manifest
        # came from (e.g. repo-by-repo), so the first N would skew toward one repo/file rather
        # than being a representative sample for a small test run.
        candidates = random.Random(seed).sample(candidates, limit)

    _write_records(candidates_path, candidates)
    return candidates


def select_candidates(
    manifest_path: Path,
    candidates_path: Path,
    required_criteria: list[str] | None = None,
    limit: int | None = None,
    seed: int | None = None,
    included_path: Path | None = None,
) -> list[MethodRecord]:
    """Convenience wrapper: writes the full included pool, then samples from it. Prefer calling
    `write_included`/`sample_candidates` separately when you want to re-sample without
    re-filtering (e.g. from the CLI, across separate invocations).
    """
    if included_path is None:
        included_path = candidates_path.parent / "included.jsonl"
    write_included(manifest_path, included_path, required_criteria)
    return sample_candidates(included_path, candidates_path, limit, seed)
