import json

from snippet_pipeline.candidates import select_candidates


def _write_manifest(path, records):
    with open(path, "w") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")


def _record(method_name, passes):
    return {
        "project": "demo",
        "filePath": "Foo.java",
        "packageName": "",
        "qualifiedClassName": "Foo",
        "methodName": method_name,
        "numParams": 1,
        "paramTypes": ["int"],
        "passesAllCriteria": passes,
        "targetMethodSignature": f"Foo#{method_name}(int)",
    }


def test_select_candidates_keeps_only_passing_records(tmp_path):
    manifest_path = tmp_path / "manifest.jsonl"
    candidates_path = tmp_path / "candidates.jsonl"
    _write_manifest(manifest_path, [
        _record("good", True),
        _record("bad1", False),
        _record("bad2", False),
        _record("alsoGood", True),
    ])

    candidates = select_candidates(manifest_path, candidates_path)

    assert {c.method_name for c in candidates} == {"good", "alsoGood"}
    assert candidates_path.exists()
    with open(candidates_path) as f:
        lines = [json.loads(line) for line in f if line.strip()]
    assert all(line["passesAllCriteria"] for line in lines)
    assert len(lines) == 2


def test_select_candidates_handles_empty_manifest(tmp_path):
    manifest_path = tmp_path / "manifest.jsonl"
    candidates_path = tmp_path / "candidates.jsonl"
    manifest_path.write_text("")

    candidates = select_candidates(manifest_path, candidates_path)

    assert candidates == []
    assert candidates_path.read_text() == ""
