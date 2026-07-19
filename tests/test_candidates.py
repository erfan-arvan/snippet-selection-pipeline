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
