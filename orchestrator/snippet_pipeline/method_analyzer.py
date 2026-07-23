"""Stage B: invoke MethodAnalyzerApp (as a CLI subprocess) over the staged repos and load its
JSONL manifest.
"""
from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import ToolsConfig


def ensure_jar_built(tools: ToolsConfig) -> Path:
    jar_path = tools.resolved_jar()
    if jar_path.exists():
        return jar_path

    method_analyzer_dir = Path(tools.method_analyzer_dir).expanduser().resolve()
    # Always use this project's own bundled wrapper rather than a configurable command - it's
    # part of this repo, so it's guaranteed to be there, and there's no reason to depend on a
    # system-wide `gradle` (which e.g. an HPC cluster may not have) for a build we ship.
    gradlew = method_analyzer_dir / "gradlew"
    # Some filesystems (seen on an HPC /project mount) don't reliably preserve git's tracked
    # executable bit on checkout - re-assert it rather than trust that git got it right.
    gradlew.chmod(0o755)
    result = subprocess.run(
        [str(gradlew), "shadowJar", "--console=plain"],
        cwd=method_analyzer_dir,
        capture_output=True,
        text=True,
        timeout=1800,
    )
    if result.returncode != 0 or not jar_path.exists():
        raise RuntimeError(
            f"Failed to build MethodAnalyzerApp fat jar in {method_analyzer_dir}:\n{result.stdout[-2000:]}\n{result.stderr[-2000:]}"
        )
    return jar_path


def run_method_analyzer(jar_path: Path, staging_root: Path, manifest_path: Path, log_path: Path) -> None:
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    result = subprocess.run(
        ["java", "-jar", str(jar_path), str(staging_root), str(manifest_path)],
        cwd=manifest_path.parent,
        capture_output=True,
        text=True,
        timeout=7200,
    )
    log_path.write_text(f"$ java -jar {jar_path} {staging_root} {manifest_path}\n\n--- stdout ---\n{result.stdout}\n--- stderr ---\n{result.stderr}\n")

    if result.returncode != 0:
        raise RuntimeError(f"MethodAnalyzerApp exited with {result.returncode}; see log at {log_path}")


@dataclass
class MethodRecord:
    raw: dict[str, Any]

    @property
    def project(self) -> str:
        return self.raw["project"]

    @property
    def file_path(self) -> str:
        return self.raw["filePath"]

    @property
    def method_name(self) -> str:
        return self.raw["methodName"]

    @property
    def qualified_class_name(self) -> str:
        return self.raw["qualifiedClassName"]

    @property
    def num_params(self) -> int:
        return self.raw.get("numParams", len(self.raw.get("paramTypes", [])))

    @property
    def target_method_signature(self) -> str:
        return self.raw["targetMethodSignature"]

    @property
    def passes_all_criteria(self) -> bool:
        return bool(self.raw["passesAllCriteria"])

    @property
    def snippet_id(self) -> str:
        # Stable, filesystem-safe id: project + class + method + param count, since a method
        # can be overloaded within the same class.
        safe_class = self.qualified_class_name.replace(".", "_")
        num_params = self.raw.get("numParams", len(self.raw.get("paramTypes", [])))
        return f"{self.project}__{safe_class}__{self.method_name}__{num_params}"


def load_manifest(manifest_path: Path) -> list[MethodRecord]:
    records = []
    with open(manifest_path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            records.append(MethodRecord(raw=json.loads(line)))
    return records
