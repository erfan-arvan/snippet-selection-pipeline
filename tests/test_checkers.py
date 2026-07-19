from snippet_pipeline.checkers import classify_diagnostics, parse_diagnostics, status_for

SAMPLE_JAVAC_OUTPUT = """\
> Task :compileJava
/home/user/snippets/foo__Sample__bar__1/src/main/java/Sample.java:14: error: [array.access.unsafe.high] array access unsafe
    return arr[i];
                ^
/home/user/snippets/foo__Sample__bar__1/src/main/java/Helper.java:3: warning: [unrelated.warning] something in a stub
    Object o = null;
               ^
2 errors
"""

NO_DIAGNOSTICS_OUTPUT = """\
> Task :compileJava
BUILD SUCCESSFUL in 2s
"""


def test_parse_diagnostics_extracts_file_line_severity_key_message():
    diagnostics = parse_diagnostics(SAMPLE_JAVAC_OUTPUT)

    assert len(diagnostics) == 2
    assert diagnostics[0]["file"].endswith("Sample.java")
    assert diagnostics[0]["line"] == "14"
    assert diagnostics[0]["severity"] == "error"
    assert diagnostics[0]["key"] == "array.access.unsafe.high"
    assert diagnostics[1]["file"].endswith("Helper.java")
    assert diagnostics[1]["severity"] == "warning"


def test_parse_diagnostics_empty_when_build_successful():
    assert parse_diagnostics(NO_DIAGNOSTICS_OUTPUT) == []


def test_classify_diagnostics_on_target_vs_elsewhere():
    raw = parse_diagnostics(SAMPLE_JAVAC_OUTPUT)

    classified = classify_diagnostics(
        raw,
        sliced_file_suffix="src/main/java/Sample.java",
        start_line=10,
        end_line=20,
    )

    on_target = [d for d in classified if d.on_target]
    elsewhere = [d for d in classified if not d.on_target]
    assert len(on_target) == 1
    assert on_target[0].line == 14
    assert len(elsewhere) == 1
    assert elsewhere[0].file.endswith("Helper.java")


def test_classify_diagnostics_line_outside_range_is_elsewhere():
    raw = parse_diagnostics(SAMPLE_JAVAC_OUTPUT)

    # target method's range no longer covers line 14
    classified = classify_diagnostics(
        raw, sliced_file_suffix="src/main/java/Sample.java", start_line=100, end_line=120
    )

    assert all(not d.on_target for d in classified if d.file.endswith("Sample.java"))


def test_status_for_passed_flagged_and_slice_suspect():
    raw = parse_diagnostics(SAMPLE_JAVAC_OUTPUT)

    all_on_target = classify_diagnostics(raw, "src/main/java/Sample.java", 10, 20)
    assert status_for(all_on_target) == "flagged"

    all_elsewhere = classify_diagnostics(raw, "src/main/java/Sample.java", 1000, 1010)
    assert status_for(all_elsewhere) == "slice_suspect"

    assert status_for([]) == "passed"
