"""Stage E: package each successful slice as a standalone, buildable Gradle module.

Each snippet becomes a real project a person can open and build independently of the
original monorepo (per the explicit requirement that slices be saved as runnable projects,
not just loose files) - with the Checker Framework Gradle plugin already wired in, ready for
Stage F to run checkers against it.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from .config import CheckerFrameworkConfig
from .method_analyzer import MethodRecord

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"


class PackagingError(RuntimeError):
    pass


def expected_sliced_relpath(record: MethodRecord) -> Path:
    """Where Specimin should have placed the target method's file, given standard Java
    package-to-directory conventions: the sliced compilation unit is named after the
    *top-level* class, even when the target method lives in a nested class.
    """
    package_name = record.raw.get("packageName", "") or ""
    qualified = record.qualified_class_name
    chain = qualified[len(package_name) + 1:] if package_name and qualified.startswith(package_name + ".") else qualified
    top_level_class = chain.split(".")[0]
    package_path = Path(*package_name.split(".")) if package_name else Path(".")
    return package_path / f"{top_level_class}.java"


def locate_method_in_slice(
    method_analyzer_jar: Path, sliced_file: Path, method_name: str, num_params: int
) -> tuple[int, int]:
    result = subprocess.run(
        ["java", "-cp", str(method_analyzer_jar), "com.github.erfanarvan.methodanalyzerapp.LocateMethod",
         str(sliced_file), method_name, str(num_params)],
        capture_output=True,
        text=True,
        timeout=60,
    )
    if result.returncode != 0:
        raise PackagingError(f"Could not re-locate {method_name} in {sliced_file}: {result.stderr.strip()}")
    start_str, end_str = result.stdout.strip().split(",")
    return int(start_str), int(end_str)


def check_for_stub_bodies(snippet_src_dir: Path) -> list[str]:
    """Specimin replaces non-target reachable methods' bodies with `throw new Error()`. If the
    target method's own logic ends up calling into a stubbed sibling (which criterion (1)
    should generally prevent, but isn't a hard guarantee - see README), the slice compiles but
    isn't actually runnable. This is a cheap textual signal, not a proof; Stage F's checker
    runs still separately verify compilability.
    """
    hits = []
    for java_file in snippet_src_dir.rglob("*.java"):
        text = java_file.read_text(errors="replace")
        if "throw new Error()" in text:
            hits.append(str(java_file.relative_to(snippet_src_dir)))
    return hits


@dataclass
class PackagedSnippet:
    snippet_id: str
    snippet_dir: Path
    metadata_path: Path
    stub_warnings: list[str]


def package_snippet(
    record: MethodRecord,
    slice_output_dir: Path,
    jar_paths: list[Path],
    method_analyzer_jar: Path,
    snippets_root: Path,
    checker_framework: CheckerFrameworkConfig,
    default_checker_processor: str,
    gradle_command: str,
) -> PackagedSnippet:
    snippet_id = record.snippet_id
    snippet_dir = snippets_root / snippet_id
    src_dir = snippet_dir / "src" / "main" / "java"
    libs_dir = snippet_dir / "libs"

    if src_dir.exists():
        shutil.rmtree(src_dir)
    src_dir.mkdir(parents=True)
    shutil.copytree(slice_output_dir, src_dir, dirs_exist_ok=True)

    libs_dir.mkdir(parents=True, exist_ok=True)
    for jar in jar_paths:
        link = libs_dir / jar.name
        if not link.exists():
            try:
                link.symlink_to(jar)
            except FileExistsError:
                pass

    sliced_relpath = expected_sliced_relpath(record)
    sliced_file = src_dir / sliced_relpath
    if not sliced_file.is_file():
        raise PackagingError(
            f"Expected sliced file not found at {sliced_file} for snippet {snippet_id} "
            f"(Specimin's output layout may not match the expected package convention)"
        )

    num_params = record.raw.get("numParams", len(record.raw.get("paramTypes", [])))
    sliced_start, sliced_end = locate_method_in_slice(
        method_analyzer_jar, sliced_file, record.method_name, num_params
    )

    stub_warnings = check_for_stub_bodies(src_dir)

    env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)))
    build_gradle = env.get_template("snippet_build.gradle.kts.j2").render(
        gradle_command=gradle_command,
        gradle_plugin_version=checker_framework.gradle_plugin_version,
        checker_framework_version=checker_framework.version,
        default_checker_processor=default_checker_processor,
    )
    (snippet_dir / "build.gradle.kts").write_text(build_gradle)
    (snippet_dir / "settings.gradle.kts").write_text(f'rootProject.name = "{snippet_id}"\n')

    metadata = {
        "snippet_id": snippet_id,
        "repo": record.project,
        "original_file": record.file_path,
        "original_start_line": record.raw.get("startLine"),
        "original_end_line": record.raw.get("endLine"),
        "method_name": record.method_name,
        "qualified_class_name": record.qualified_class_name,
        "num_params": num_params,
        "target_method_signature": record.target_method_signature,
        "sliced_file": str(sliced_file.relative_to(snippet_dir)),
        "sliced_start_line": sliced_start,
        "sliced_end_line": sliced_end,
        "stub_body_warnings": stub_warnings,
    }
    metadata_path = snippet_dir / "snippet.json"
    metadata_path.write_text(json.dumps(metadata, indent=2))

    return PackagedSnippet(
        snippet_id=snippet_id, snippet_dir=snippet_dir, metadata_path=metadata_path, stub_warnings=stub_warnings
    )
