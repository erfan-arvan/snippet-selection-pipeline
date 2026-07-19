"""Loads and validates the pipeline's YAML configuration.

Kept as plain dataclasses (no pydantic/etc.) since the schema is small and stable; this
avoids adding a dependency for what's ultimately a handful of typed fields.
"""
from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml


@dataclass
class RepoConfig:
    name: str
    path: Optional[str]
    commit: Optional[str]
    build_system: str  # "gradle" or "maven"
    # Escape hatch: a pre-computed, colon/newline-separated classpath file, for repos whose
    # build can't be auto-resolved generically (see classpath.py's limitations).
    classpath_override: Optional[str] = None

    def resolved_path(self) -> Path:
        if not self.path:
            raise ValueError(
                f"repo '{self.name}' has no local path set in pipeline.yaml - "
                "clone it yourself and fill in its `path`."
            )
        return Path(self.path).expanduser().resolve()


@dataclass
class ToolsConfig:
    method_analyzer_dir: str
    specimin_dir: str
    method_analyzer_jar: Optional[str] = None  # default: <method_analyzer_dir>/build/libs/method-analyzer-all.jar

    def resolved_jar(self) -> Path:
        if self.method_analyzer_jar:
            return Path(self.method_analyzer_jar).expanduser().resolve()
        return Path(self.method_analyzer_dir).expanduser().resolve() / "build" / "libs" / "method-analyzer-all.jar"


@dataclass
class FilteringConfig:
    min_loc: int = 20
    max_loc: int = 30


@dataclass
class CheckerFrameworkConfig:
    # Verify these against https://github.com/typetools/checker-framework/releases and
    # https://plugins.gradle.org/plugin/org.checkerframework before running - Checker
    # Framework ships frequently and a stale version here will just fail the Gradle build,
    # not silently misbehave.
    version: str = "4.2.1"
    gradle_plugin_version: str = "0.6.42"


@dataclass
class CheckerSpec:
    id: str
    processor: str


@dataclass
class PipelineConfig:
    output_dir: str
    tools: ToolsConfig
    repos: list[RepoConfig]
    checkers: list[CheckerSpec]
    filtering: FilteringConfig = field(default_factory=FilteringConfig)
    checker_framework: CheckerFrameworkConfig = field(default_factory=CheckerFrameworkConfig)
    gradle_command: str = "gradle"
    run_id: Optional[str] = None

    def _last_run_marker(self) -> Path:
        return Path(self.output_dir).expanduser().resolve() / ".last_run_id"

    def start_new_run(self) -> str:
        """Used only by the pipeline's entry stage (`filter`): mints a fresh run id (unless
        one was pinned explicitly in the YAML or via --run-id) and persists it as "the most
        recent run" so later stages - each a separate process, each reloading this config
        from scratch - can find it without the caller having to pass --run-id every time.
        """
        run_id = self.run_id or datetime.datetime.now().strftime("run-%Y%m%d-%H%M%S")
        marker = self._last_run_marker()
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(run_id)
        return run_id

    def resolve_existing_run_id(self) -> str:
        """Used by every stage after `filter`: an explicit run id (YAML `run_id` or --run-id)
        always wins; otherwise falls back to whatever `filter` last recorded. Raises rather
        than silently minting a new (empty) run directory if neither is available, since that
        would look like a mysteriously empty pipeline run instead of a clear "run filter
        first" error.
        """
        if self.run_id:
            return self.run_id
        marker = self._last_run_marker()
        if not marker.is_file():
            raise RuntimeError(
                f"No run id given and no previous run recorded at {marker}. "
                "Run the 'filter' stage first, or pass --run-id explicitly."
            )
        return marker.read_text().strip()

    def run_output_dir(self, run_id: str) -> Path:
        return Path(self.output_dir).expanduser().resolve() / run_id


def _load_checkers(checkers_path: Path) -> list[CheckerSpec]:
    with open(checkers_path) as f:
        raw = yaml.safe_load(f) or {}
    return [CheckerSpec(id=c["id"], processor=c["processor"]) for c in raw.get("checkers", [])]


def _resolve_relative(base_dir: Path, value: Optional[str]) -> Optional[str]:
    """Resolves a possibly-relative path from the YAML against the YAML file's own
    directory, not the process's current working directory - otherwise `gradle_command`
    invocations from a different cwd than `config/` would silently point at the wrong place.
    """
    if not value:
        return value
    path = Path(value).expanduser()
    return str(path if path.is_absolute() else (base_dir / path).resolve())


def load_config(pipeline_yaml_path: str | Path) -> PipelineConfig:
    pipeline_yaml_path = Path(pipeline_yaml_path).expanduser().resolve()
    base_dir = pipeline_yaml_path.parent
    with open(pipeline_yaml_path) as f:
        raw = yaml.safe_load(f) or {}

    tools_raw = raw.get("tools", {})
    tools = ToolsConfig(
        method_analyzer_dir=_resolve_relative(base_dir, tools_raw["method_analyzer_dir"]),
        specimin_dir=_resolve_relative(base_dir, tools_raw["specimin_dir"]),
        method_analyzer_jar=_resolve_relative(base_dir, tools_raw.get("method_analyzer_jar")),
    )

    repos = [
        RepoConfig(
            name=r["name"],
            path=_resolve_relative(base_dir, r.get("path")),
            commit=r.get("commit"),
            build_system=r.get("build_system", "gradle"),
            classpath_override=_resolve_relative(base_dir, r.get("classpath_override")),
        )
        for r in raw.get("repos", [])
    ]

    filtering_raw = raw.get("filtering", {})
    filtering = FilteringConfig(
        min_loc=filtering_raw.get("min_loc", 20),
        max_loc=filtering_raw.get("max_loc", 30),
    )

    cf_raw = raw.get("checker_framework", {})
    checker_framework = CheckerFrameworkConfig(
        version=cf_raw.get("version", CheckerFrameworkConfig.version),
        gradle_plugin_version=cf_raw.get("gradle_plugin_version", CheckerFrameworkConfig.gradle_plugin_version),
    )

    checkers_file = raw.get("checkers_file", "checkers.yaml")
    checkers_path = Path(checkers_file)
    if not checkers_path.is_absolute():
        checkers_path = pipeline_yaml_path.parent / checkers_path
    checkers = _load_checkers(checkers_path)

    return PipelineConfig(
        output_dir=_resolve_relative(base_dir, raw.get("output_dir", "./output")),
        tools=tools,
        repos=repos,
        checkers=checkers,
        filtering=filtering,
        checker_framework=checker_framework,
        gradle_command=raw.get("gradle_command", "gradle"),
        run_id=raw.get("run_id"),
    )
