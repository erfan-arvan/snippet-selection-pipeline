import importlib.util
import json
from pathlib import Path

import openpyxl
import pytest

# scripts/ isn't part of the installed snippet_pipeline package, so load it directly by path.
SCRIPT_PATH = Path(__file__).resolve().parent.parent / "orchestrator" / "scripts" / "convert_legacy_xlsx.py"
_spec = importlib.util.spec_from_file_location("convert_legacy_xlsx", SCRIPT_PATH)
convert_legacy_xlsx = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(convert_legacy_xlsx)

HEADER = [
    "Method", "Path", "Class", "Package", "ReturnType", "isFinal", "isAbstract", "isDefault", "isStatic",
    "NumParams", "ParamTypes", "parNumStandardTypes", "parNumCustomTypes", "parNumUnresolvedTypes",
    "AccessModifier", "Annotations", "Javadoc", "Expressions", "ExpressionTypes", "expNumStandardTypes",
    "expNumCustomTypes", "expNumUnresolvedTypes", "AllStandard", "AllCustomAndUnresolved", "project",
    "CleanLoc", "CleanLoc",
]


def _write_fixture(path, rows):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(HEADER)
    for row in rows:
        ws.append(row)
    wb.save(path)


def _row(method, path, num_params, param_types_sanitized, is_static, return_type, javadoc,
         annotations, all_custom_and_unresolved, clean_loc_authoritative, clean_loc_stale):
    return [
        method, path, "MathUtil", "com.example.util", return_type, "FALSE", "FALSE", "FALSE",
        "TRUE" if is_static else "FALSE", num_params, param_types_sanitized, 0, 0, 0, "public",
        annotations, javadoc, "", "", 0, 0, 0, 0, all_custom_and_unresolved, "demo",
        clean_loc_authoritative, clean_loc_stale,
    ]


@pytest.fixture
def fixture_path(tmp_path):
    rows = [
        _row("sumValues", "repos/demo/src/com/example/util/MathUtil.java", 1, "ob int cb",
             True, "int", "Sums values.", "", 0, 25, 20),
        _row("combine", "repos/demo/src/com/example/util/MathUtil.java", 2, "ob int java.lang.String cb",
             True, "int", "Combines values.", "", 0, 22, 18),
        _row("mapify", "repos/demo/src/com/example/util/MathUtil.java", 2, "ob Map<String Integer> int cb",
             True, "int", "Ambiguous multi-param types.", "", 0, 24, 19),
        _row("notStatic", "repos/demo/src/com/example/util/MathUtil.java", 1, "ob int cb",
             False, "int", "Not static.", "", 0, 25, 20),
        _row("tooLong", "repos/demo/src/com/example/util/MathUtil.java", 1, "ob int cb",
             True, "int", "Too long.", "", 0, 50, 45),
        _row("usesCustom", "repos/demo/src/com/example/util/MathUtil.java", 1, "ob CustomType cb",
             True, "int", "Uses a custom type.", "", 1, 22, 18),
    ]
    path = tmp_path / "legacy.xlsx"
    _write_fixture(path, rows)
    return path


def _load_by_method(jsonl_path):
    return {json.loads(line)["methodName"]: json.loads(line) for line in open(jsonl_path)}


def test_single_param_method_converts_and_passes(fixture_path, tmp_path):
    output = tmp_path / "manifest.jsonl"
    convert_legacy_xlsx.convert(str(fixture_path), str(output))

    records = _load_by_method(output)
    assert records["sumValues"]["passesAllCriteria"] is True
    assert records["sumValues"]["paramTypes"] == ["int"]
    assert records["sumValues"]["targetMethodSignature"] == "com.example.util.MathUtil#sumValues(int)"


def test_cleanly_recoverable_multi_param_method_converts_and_passes(fixture_path, tmp_path):
    output = tmp_path / "manifest.jsonl"
    convert_legacy_xlsx.convert(str(fixture_path), str(output))

    records = _load_by_method(output)
    assert records["combine"]["passesAllCriteria"] is True
    assert records["combine"]["paramTypes"] == ["int", "java.lang.String"]


def test_ambiguous_multi_param_method_is_dropped_not_guessed(fixture_path, tmp_path):
    output = tmp_path / "manifest.jsonl"
    convert_legacy_xlsx.convert(str(fixture_path), str(output))

    records = _load_by_method(output)
    assert "mapify" not in records  # dropped entirely, not written with a guessed/wrong signature


def test_failing_criteria_rows_are_still_written_with_passes_false(fixture_path, tmp_path):
    output = tmp_path / "manifest.jsonl"
    convert_legacy_xlsx.convert(str(fixture_path), str(output))

    records = _load_by_method(output)
    assert records["notStatic"]["passesAllCriteria"] is False
    assert records["notStatic"]["criteria"]["isStatic"] is False

    assert records["tooLong"]["passesAllCriteria"] is False
    assert records["tooLong"]["criteria"]["locInRange"] is False

    assert records["usesCustom"]["passesAllCriteria"] is False
    assert records["usesCustom"]["criteria"]["allTypesJdk"] is False


def test_uses_first_cleanloc_column_not_the_duplicate(fixture_path, tmp_path):
    # Both CleanLoc columns exist in the fixture with different values (25/20 for sumValues) -
    # the first (25, in range) must be the one used, matching the user's confirmation.
    output = tmp_path / "manifest.jsonl"
    convert_legacy_xlsx.convert(str(fixture_path), str(output))

    records = _load_by_method(output)
    assert records["sumValues"]["cleanLoc"] == 25


def test_staging_relative_file_path_strips_repos_prefix(fixture_path, tmp_path):
    output = tmp_path / "manifest.jsonl"
    convert_legacy_xlsx.convert(str(fixture_path), str(output))

    records = _load_by_method(output)
    assert records["sumValues"]["filePath"] == "source/src/com/example/util/MathUtil.java"
