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


def test_relative_tool_paths_resolve_against_yaml_location_not_cwd():
    config = load_config(REPO_ROOT / "config" / "pipeline.yaml")

    # tools.method_analyzer_dir is "../tools/method-analyzer" relative to config/pipeline.yaml
    assert Path(config.tools.method_analyzer_dir) == (REPO_ROOT / "tools" / "method-analyzer").resolve()


def test_repo_names_match_the_sixteen_target_projects():
    config = load_config(REPO_ROOT / "config" / "pipeline.yaml")
    names = {r.name for r in config.repos}
    assert names == {
        "netty", "spring-framework", "kafka", "druid", "dubbo", "libgdx",
        "spring-boot", "rxjava", "selenium", "mybatis-3", "guava",
        "javaguide", "ghidra", "hudi", "apollo", "WxJava",
    }
