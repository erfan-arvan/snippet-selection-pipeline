import pytest

from snippet_pipeline.config import CheckerFrameworkConfig, FilteringConfig, PipelineConfig, ToolsConfig


def _config(tmp_path, run_id=None):
    return PipelineConfig(
        output_dir=str(tmp_path / "output"),
        tools=ToolsConfig(method_analyzer_dir="x", specimin_dir="y"),
        repos=[],
        checkers=[],
        filtering=FilteringConfig(),
        checker_framework=CheckerFrameworkConfig(),
        run_id=run_id,
    )


def test_later_stage_finds_the_run_id_that_filter_started(tmp_path):
    """Reproduces the real bug this was written to fix: `filter` and a later stage (`select`,
    `slice`, ...) are separate process invocations, each calling load_config() fresh. Without
    persisting the run id somewhere, a later stage minting its own fresh timestamp would look
    in a run directory `filter` never wrote anything to.
    """
    filter_config = _config(tmp_path)
    run_id_from_filter = filter_config.start_new_run()

    # A brand new PipelineConfig instance, as a separate process would construct via
    # load_config() - simulates the process boundary between CLI invocations.
    select_config = _config(tmp_path)
    run_id_seen_by_select = select_config.resolve_existing_run_id()

    assert run_id_seen_by_select == run_id_from_filter


def test_explicit_run_id_overrides_the_recorded_one(tmp_path):
    filter_config = _config(tmp_path)
    filter_config.start_new_run()

    explicit_config = _config(tmp_path, run_id="some-older-run")
    assert explicit_config.resolve_existing_run_id() == "some-older-run"


def test_resolve_existing_run_id_fails_clearly_when_nothing_recorded(tmp_path):
    config = _config(tmp_path)
    with pytest.raises(RuntimeError, match="Run the 'filter' stage first"):
        config.resolve_existing_run_id()
