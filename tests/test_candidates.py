import json

from snippet_pipeline.candidates import select_candidates
from snippet_pipeline.config import ALL_CRITERIA


def _write_manifest(path, records):
    with open(path, "w") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")


def _record(method_name, criteria_overrides=None):
    criteria = {name: True for name in ALL_CRITERIA}
    if criteria_overrides:
        criteria.update(criteria_overrides)
    return {
        "project": "demo",
        "filePath": "Foo.java",
        "packageName": "",
        "qualifiedClassName": "Foo",
        "methodName": method_name,
        "numParams": 1,
        "paramTypes": ["int"],
        "criteria": criteria,
        "passesAllCriteria": all(criteria.values()),
        "targetMethodSignature": f"Foo#{method_name}(int)",
    }


def test_select_candidates_keeps_only_passing_records(tmp_path):
    manifest_path = tmp_path / "manifest.jsonl"
    candidates_path = tmp_path / "candidates.jsonl"
    _write_manifest(manifest_path, [
        _record("good"),
        _record("bad1", {"isStatic": False}),
        _record("bad2", {"locInRange": False}),
        _record("alsoGood"),
    ])

    candidates = select_candidates(manifest_path, candidates_path)

    assert {c.method_name for c in candidates} == {"good", "alsoGood"}
    assert candidates_path.exists()
    with open(candidates_path) as f:
        lines = [json.loads(line) for line in f if line.strip()]
    assert len(lines) == 2


def test_select_candidates_handles_empty_manifest(tmp_path):
    manifest_path = tmp_path / "manifest.jsonl"
    candidates_path = tmp_path / "candidates.jsonl"
    manifest_path.write_text("")

    candidates = select_candidates(manifest_path, candidates_path)

    assert candidates == []
    assert candidates_path.read_text() == ""


def test_custom_required_criteria_ignores_the_rest(tmp_path):
    manifest_path = tmp_path / "manifest.jsonl"
    candidates_path = tmp_path / "candidates.jsonl"
    _write_manifest(manifest_path, [
        # Fails isStatic and allTypesJdk, but those aren't required below - should still pass.
        _record("notStaticNotJdk", {"isStatic": False, "allTypesJdk": False}),
        # Fails locInRange, which *is* required below - should be excluded.
        _record("tooShort", {"locInRange": False}),
    ])

    candidates = select_candidates(
        manifest_path, candidates_path,
        required_criteria=["paramAndReturnOk", "locInRange", "noAnnotations"],
    )

    assert {c.method_name for c in candidates} == {"notStaticNotJdk"}


def test_missing_criteria_field_fails_closed(tmp_path):
    # A record with no "criteria" key at all (e.g. hand-written test data, or a future schema
    # gap) must not silently pass - missing information should never look like a pass.
    manifest_path = tmp_path / "manifest.jsonl"
    candidates_path = tmp_path / "candidates.jsonl"
    _write_manifest(manifest_path, [
        {"project": "demo", "filePath": "F.java", "qualifiedClassName": "F", "methodName": "noCriteria",
         "numParams": 1, "paramTypes": ["int"], "targetMethodSignature": "F#noCriteria(int)"},
    ])

    candidates = select_candidates(manifest_path, candidates_path)

    assert candidates == []


def test_limit_samples_randomly_not_the_first_n(tmp_path):
    manifest_path = tmp_path / "manifest.jsonl"
    candidates_path = tmp_path / "candidates.jsonl"
    _write_manifest(manifest_path, [_record(f"method{i}") for i in range(100)])

    candidates_seed1 = select_candidates(manifest_path, candidates_path, limit=5, seed=1)
    assert len(candidates_seed1) == 5
    # Not just the first 5 in manifest order - a real (if not airtight) check that this is an
    # actual sample rather than a silent "first N".
    assert {c.method_name for c in candidates_seed1} != {f"method{i}" for i in range(5)}

    with open(candidates_path) as f:
        written = [json.loads(line) for line in f if line.strip()]
    assert len(written) == 5


def test_limit_is_reproducible_with_the_same_seed(tmp_path):
    manifest_path = tmp_path / "manifest.jsonl"
    candidates_path = tmp_path / "candidates.jsonl"
    _write_manifest(manifest_path, [_record(f"method{i}") for i in range(100)])

    first = select_candidates(manifest_path, candidates_path, limit=10, seed=42)
    second = select_candidates(manifest_path, candidates_path, limit=10, seed=42)

    assert {c.method_name for c in first} == {c.method_name for c in second}


def test_limit_larger_than_candidate_set_returns_everything(tmp_path):
    manifest_path = tmp_path / "manifest.jsonl"
    candidates_path = tmp_path / "candidates.jsonl"
    _write_manifest(manifest_path, [_record("a"), _record("b")])

    candidates = select_candidates(manifest_path, candidates_path, limit=1000, seed=1)

    assert {c.method_name for c in candidates} == {"a", "b"}
