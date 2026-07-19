import csv
import json

from snippet_pipeline.checkers import CheckerRunResult, Diagnostic
from snippet_pipeline.stats import print_summary, write_stats


def _result(snippet_id, checker_id, status, log_path):
    diag = []
    if status == "flagged":
        diag = [Diagnostic(file="Foo.java", line=5, severity="error", key="k", message="m", on_target=True)]
    elif status == "slice_suspect":
        diag = [Diagnostic(file="Foo.java", line=999, severity="warning", key="k", message="m", on_target=False)]
    return CheckerRunResult(
        snippet_id=snippet_id, checker_id=checker_id, status=status,
        on_target_count=sum(1 for d in diag if d.on_target),
        elsewhere_count=sum(1 for d in diag if not d.on_target),
        diagnostics=diag, log_path=log_path, returncode=0 if status != "run_error" else 1,
    )


def test_write_stats_produces_csv_and_jsonl_with_log_paths(tmp_path):
    results = [
        _result("snippetA", "nullness", "passed", tmp_path / "logs/snippetA/nullness.log"),
        _result("snippetA", "index", "flagged", tmp_path / "logs/snippetA/index.log"),
        _result("snippetB", "nullness", "slice_suspect", tmp_path / "logs/snippetB/nullness.log"),
    ]
    stats_dir = tmp_path / "stats"

    csv_path, jsonl_path = write_stats(results, stats_dir)

    with open(csv_path) as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 3
    assert all(row["log_path"] for row in rows)
    flagged_row = next(r for r in rows if r["status"] == "flagged")
    assert flagged_row["log_path"] == str(tmp_path / "logs/snippetA/index.log")

    with open(jsonl_path) as f:
        lines = [json.loads(line) for line in f]
    assert len(lines) == 3
    assert any(line["diagnostics"] for line in lines if line["status"] == "flagged")


def test_print_summary_includes_log_root_and_flagged_rows(tmp_path, capsys):
    results = [
        _result("snippetA", "nullness", "passed", tmp_path / "logs/snippetA/nullness.log"),
        _result("snippetA", "index", "flagged", tmp_path / "logs/snippetA/index.log"),
    ]
    stats_paths = write_stats(results, tmp_path / "stats")
    logs_root = tmp_path / "logs"

    summary = print_summary(results, logs_root, stats_paths)
    captured = capsys.readouterr()

    assert str(logs_root) in summary
    assert str(logs_root) in captured.out
    assert "snippetA / index" in summary
    assert "flagged" in summary
