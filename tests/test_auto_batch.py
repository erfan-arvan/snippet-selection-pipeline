import json

from snippet_pipeline import auto_batch
from snippet_pipeline.checkers import CheckerRunResult
from snippet_pipeline.config import ALL_CRITERIA


def _write_included(path, count):
    with open(path, "w") as f:
        for i in range(count):
            f.write(json.dumps({
                "project": "demo", "filePath": "Foo.java", "packageName": "", "qualifiedClassName": "Foo",
                "methodName": f"m{i}", "numParams": 1, "paramTypes": ["int"],
                "criteria": {name: True for name in ALL_CRITERIA},
                "passesAllCriteria": True, "targetMethodSignature": f"Foo#m{i}(int)",
            }) + "\n")


def _result(snippet_id, checker_id, status):
    return CheckerRunResult(
        snippet_id=snippet_id, checker_id=checker_id, status=status,
        on_target_count=1 if status == "flagged" else 0, elsewhere_count=0,
        diagnostics=[], log_path="/dev/null", returncode=1,
    )


def test_flagged_counts_splits_nullness_from_others():
    results = [
        _result("a", "nullness", "flagged"),
        _result("a", "index", "flagged"),
        _result("a", "regex", "passed"),
        _result("b", "nullness", "flagged"),
    ]
    total, non_nullness = auto_batch._flagged_counts(results)
    assert total == 3
    assert non_nullness == 1


def test_run_auto_batch_stops_once_target_met(tmp_path, monkeypatch):
    included_path = tmp_path / "included.jsonl"
    _write_included(included_path, 3000)
    run_dir = tmp_path / "run"

    # Batch 1: not enough yet. Batch 2: pushes total >= 100 and non-nullness > 50 together.
    batch_results = [
        [_result(f"b1-{i}", "nullness", "flagged") for i in range(40)],
        [_result(f"b2-{i}", "nullness", "flagged") for i in range(40)]
        + [_result(f"b2-{i}", "index", "flagged") for i in range(60)],
        [_result(f"b3-{i}", "nullness", "flagged") for i in range(999)],  # must not be reached
    ]
    calls = []

    def fake_run_batch(config, run_dir_, batch, repo_cache, batch_num):
        calls.append(batch_num)
        return batch_results[batch_num - 1]

    monkeypatch.setattr(auto_batch, "_run_batch", fake_run_batch)
    monkeypatch.setattr(auto_batch.stats_stage, "write_stats", lambda results, stats_dir: (None, None))
    monkeypatch.setattr(auto_batch.stats_stage, "print_summary", lambda *a, **k: None)

    auto_batch.run_auto_batch(
        config=object(), run_dir=run_dir, included_path=included_path,
        batch_size=1000, min_total_flagged=100, min_non_nullness_flagged=50, seed=1,
    )

    assert calls == [1, 2]  # never touched batch 3
    state = json.loads(auto_batch._state_path(run_dir).read_text())
    assert state["batches_run"] == 2
    cumulative = auto_batch._load_cumulative_results(run_dir)
    total, non_nullness = auto_batch._flagged_counts(cumulative)
    assert total == 140
    assert non_nullness == 60


def test_run_auto_batch_reports_pool_exhausted(tmp_path, monkeypatch):
    included_path = tmp_path / "included.jsonl"
    _write_included(included_path, 50)  # smaller than batch_size, and never enough flagged
    run_dir = tmp_path / "run"

    monkeypatch.setattr(auto_batch, "_run_batch", lambda *a, **k: [_result("x", "nullness", "passed")])
    monkeypatch.setattr(auto_batch.stats_stage, "write_stats", lambda results, stats_dir: (None, None))
    monkeypatch.setattr(auto_batch.stats_stage, "print_summary", lambda *a, **k: None)

    auto_batch.run_auto_batch(
        config=object(), run_dir=run_dir, included_path=included_path,
        batch_size=1000, min_total_flagged=100, min_non_nullness_flagged=50, seed=1,
    )

    state = json.loads(auto_batch._state_path(run_dir).read_text())
    assert state["next_offset"] == 50
    assert state["batches_run"] == 1


def test_run_auto_batch_resumes_without_rerunning_completed_batches(tmp_path, monkeypatch):
    included_path = tmp_path / "included.jsonl"
    _write_included(included_path, 3000)
    run_dir = tmp_path / "run"

    monkeypatch.setattr(auto_batch.stats_stage, "write_stats", lambda results, stats_dir: (None, None))
    monkeypatch.setattr(auto_batch.stats_stage, "print_summary", lambda *a, **k: None)

    calls = []
    monkeypatch.setattr(
        auto_batch, "_run_batch",
        lambda config, run_dir_, batch, repo_cache, batch_num: (calls.append(batch_num), [_result(f"b{batch_num}", "nullness", "passed")])[1],
    )

    # First invocation: target unreachable (all "passed"), pool exhausts after 3 batches.
    auto_batch.run_auto_batch(
        config=object(), run_dir=run_dir, included_path=included_path,
        batch_size=1000, min_total_flagged=100, min_non_nullness_flagged=50, seed=1,
    )
    assert calls == [1, 2, 3]

    # Second invocation with the same seed/run_dir must not redo batches 1-3.
    calls.clear()
    auto_batch.run_auto_batch(
        config=object(), run_dir=run_dir, included_path=included_path,
        batch_size=1000, min_total_flagged=100, min_non_nullness_flagged=50, seed=1,
    )
    assert calls == []  # pool was already exhausted; nothing new to run
