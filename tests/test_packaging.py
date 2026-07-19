from pathlib import Path

from snippet_pipeline.method_analyzer import MethodRecord
from snippet_pipeline.packaging import expected_sliced_relpath


def _record(package_name, qualified_class_name, method_name="foo"):
    return MethodRecord(raw={
        "project": "demo",
        "filePath": "Sample.java",
        "packageName": package_name,
        "qualifiedClassName": qualified_class_name,
        "methodName": method_name,
        "numParams": 1,
        "paramTypes": ["int"],
        "passesAllCriteria": True,
        "targetMethodSignature": f"{qualified_class_name}#{method_name}(int)",
    })


def test_expected_path_for_top_level_class_no_package():
    record = _record("", "Sample")
    assert expected_sliced_relpath(record) == Path("Sample.java")


def test_expected_path_for_top_level_class_with_package():
    record = _record("com.example", "com.example.Sample")
    assert expected_sliced_relpath(record) == Path("com/example/Sample.java")


def test_expected_path_for_nested_class_uses_top_level_class_file():
    # A method inside a nested class "Outer.Inner" still lives in Outer.java.
    record = _record("com.example", "com.example.Outer.Inner")
    assert expected_sliced_relpath(record) == Path("com/example/Outer.java")


def test_snippet_id_disambiguates_overloads_by_param_count():
    one_param = MethodRecord(raw={
        "project": "demo", "filePath": "S.java", "qualifiedClassName": "S",
        "methodName": "foo", "numParams": 1, "paramTypes": ["int"], "passesAllCriteria": True,
        "targetMethodSignature": "S#foo(int)",
    })
    two_param = MethodRecord(raw={
        "project": "demo", "filePath": "S.java", "qualifiedClassName": "S",
        "methodName": "foo", "numParams": 2, "paramTypes": ["int", "int"], "passesAllCriteria": True,
        "targetMethodSignature": "S#foo(int, int)",
    })
    assert one_param.snippet_id != two_param.snippet_id
