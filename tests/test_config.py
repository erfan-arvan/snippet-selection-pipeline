from pathlib import Path

from snippet_pipeline.config import load_config

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_loads_real_pipeline_config_with_16_repos_and_9_checkers():
    config = load_config(REPO_ROOT / "config" / "pipeline.yaml")

    assert len(config.repos) == 16
    assert len(config.checkers) == 9
    assert {c.id for c in config.checkers} == {
        "nullness", "index", "optional", "interning", "resourceleak",
        "sqlquotes", "regex", "formatter", "i18n",
    }


def test_relative_tool_paths_resolve_against_yaml_location_not_cwd(tmp_path):
    # Uses its own throwaway fixture rather than config/pipeline.yaml - that file is meant to
    # be edited by whoever runs the pipeline (real repo paths, real tool dirs), so a test
    # asserting on its exact path-resolution behavior would break the moment someone
    # legitimately customizes it (as happened here: swapping a relative tools path for an
    # absolute one on a system where /project is itself a symlink to /mmfs1/project tripped
    # this exact assertion, even though nothing was actually wrong).
    # Mirrors the real repo layout: config/pipeline.yaml sits next to checkers.yaml, with
    # tools/ as a sibling directory one level up.
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "checkers.yaml").write_text("checkers: []\n")
    (config_dir / "pipeline.yaml").write_text(
        "output_dir: ./output\n"
        "tools:\n"
        "  method_analyzer_dir: ../tools/method-analyzer\n"
        "  specimin_dir: ../tools/specimin\n"
        "checkers_file: checkers.yaml\n"
        "repos: []\n"
    )
    (tmp_path / "tools" / "method-analyzer").mkdir(parents=True)

    config = load_config(config_dir / "pipeline.yaml")

    assert Path(config.tools.method_analyzer_dir) == (tmp_path / "tools" / "method-analyzer").resolve()


def test_repo_names_match_the_sixteen_target_projects():
    config = load_config(REPO_ROOT / "config" / "pipeline.yaml")
    names = {r.name for r in config.repos}
    assert names == {
        "netty", "spring-framework", "kafka", "druid", "dubbo", "libgdx",
        "spring-boot", "rxjava", "selenium", "mybatis-3", "guava",
        "javaguide", "ghidra", "hudi", "apollo", "WxJava",
    }
