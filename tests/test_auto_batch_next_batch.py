"""Running "the next batch" of an auto run whose targets are already met, without losing the
diagnostics that earlier batches recorded in stats/results.jsonl."""
import json

from snippet_pipeline import auto_batch, stats
from snippet_pipeline.checkers import CheckerRunResult, Diagnostic
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


def _flagged(snippet_id, checker_id, key="argument"):
    return CheckerRunResult(
        snippet_id=snippet_id, checker_id=checker_id, status="flagged", on_target_count=1, elsewhere_count=0,
        diagnostics=[Diagnostic(file="Foo.java", line=3, severity="warning", key=key, message="msg", on_target=True)],
        log_path="/dev/null", returncode=0,
    )


def _old_style_run(run_dir, results):
    """A run made before auto_batch_results.jsonl stored diagnostics: they exist only in results.jsonl."""
    (run_dir / "stats").mkdir(parents=True)
    with open(run_dir / "stats" / "auto_batch_results.jsonl", "w") as f:
        for r in results:
            f.write(json.dumps({"snippet_id": r.snippet_id, "checker_id": r.checker_id, "status": r.status,
                                "on_target_count": 1, "elsewhere_count": 0, "returncode": 0,
                                "log_path": "/dev/null"}) + "\n")
    stats.write_stats(results, run_dir / "stats")
    auto_batch._save_state(run_dir, {"seed": 1, "next_offset": 1000, "batches_run": 1})


def _quiet(monkeypatch):
    monkeypatch.setattr(auto_batch.stats_stage, "print_summary", lambda *a, **k: None)


def test_max_batches_runs_next_batch_even_when_targets_already_met(tmp_path, monkeypatch):
    included = tmp_path / "included.jsonl"
    _write_included(included, 3000)
    run_dir = tmp_path / "run"
    _old_style_run(run_dir, [_flagged(f"old-{i}", "index") for i in range(200)])  # targets long met
    calls = []
    monkeypatch.setattr(auto_batch, "_run_batch",
                        lambda c, r, batch, cache, n: calls.append(n) or [_flagged(f"new-{n}", "index")])
    _quiet(monkeypatch)

    auto_batch.run_auto_batch(config=object(), run_dir=run_dir, included_path=included,
                              batch_size=1000, min_total_flagged=100, min_non_nullness_flagged=50,
                              seed=1, max_batches=1)

    assert calls == [2]  # exactly one new batch, continuing after the one already run
    state = json.loads(auto_batch._state_path(run_dir).read_text())
    assert state["next_offset"] == 2000 and state["batches_run"] == 2


def test_resumed_run_keeps_earlier_diagnostics_in_results_jsonl(tmp_path, monkeypatch):
    included = tmp_path / "included.jsonl"
    _write_included(included, 3000)
    run_dir = tmp_path / "run"
    _old_style_run(run_dir, [_flagged("old-0", "nullness", key="return")])
    monkeypatch.setattr(auto_batch, "_run_batch", lambda c, r, batch, cache, n: [_flagged("new-0", "index")])
    _quiet(monkeypatch)

    auto_batch.run_auto_batch(config=object(), run_dir=run_dir, included_path=included,
                              batch_size=1000, seed=1, max_batches=1)

    rows = {(d["snippet_id"], d["checker_id"]): d
            for d in map(json.loads, (run_dir / "stats" / "results.jsonl").read_text().splitlines())}
    assert rows[("old-0", "nullness")]["diagnostics"][0]["key"] == "return"   # not wiped
    assert rows[("new-0", "index")]["diagnostics"][0]["key"] == "argument"    # new batch recorded
    # and the new batch's diagnostics are now in auto_batch_results.jsonl itself
    auto_rows = [json.loads(l) for l in (run_dir / "stats" / "auto_batch_results.jsonl").read_text().splitlines()]
    assert auto_rows[-1]["diagnostics"][0]["key"] == "argument"
