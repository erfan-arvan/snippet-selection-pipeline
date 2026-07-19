"""Stage D: invoke Specimin to slice each candidate method into a minimized program.

Important caveat carried over from planning (see README "Limitations"): Specimin's own docs
state its output is "not intended to produce runnable output... only useful for static
analysis" - any non-target method reachable from the target gets its body replaced with
`throw new Error()`. Criterion (1) (all-JDK-types) should mean a target method never calls
back into other project-internal methods, so this normally shouldn't bite, but Stage F's
packaging step still checks for stub bodies as a safety net (see packaging.py).
"""
from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from .classpath import ResolvedRepo
from .method_analyzer import MethodRecord


class SourceRootNotFoundError(RuntimeError):
    pass


def find_source_root_and_target_file(
    resolved_repo: ResolvedRepo, staging_dir: Path, record: MethodRecord
) -> tuple[Path, str]:
    """Maps a manifest record's staging-relative file path back to (a) which of the repo's
    discovered source roots it lives under and (b) its path relative to that root - the two
    things Specimin's --root/--targetFile need.
    """
    absolute_file = (staging_dir / record.file_path).resolve()
    for source_root in resolved_repo.source_roots:
        source_root = source_root.resolve()
        try:
            relative = absolute_file.relative_to(source_root)
        except ValueError:
            continue
        return source_root, str(relative)
    raise SourceRootNotFoundError(
        f"{record.file_path} in repo '{resolved_repo.repo.name}' is not under any discovered source root: "
        f"{resolved_repo.source_roots}"
    )


def materialize_jar_dir(resolved_repo: ResolvedRepo, jar_dir: Path) -> Path:
    """Specimin's --jarPath wants a directory of jars, not a list - symlink farm, built once
    per repo and reused across all of that repo's candidates."""
    jar_dir.mkdir(parents=True, exist_ok=True)
    for jar in resolved_repo.classpath_jars:
        link = jar_dir / jar.name
        if not link.exists():
            try:
                link.symlink_to(jar)
            except FileExistsError:
                pass
    return jar_dir


@dataclass
class SliceResult:
    snippet_id: str
    success: bool
    output_dir: Path
    log_path: Path


def slice_candidate(
    specimin_dir: Path,
    gradle_command: str,
    source_root: Path,
    target_file: str,
    target_method_signature: str,
    jar_dir: Path,
    output_dir: Path,
    log_path: Path,
) -> SliceResult:
    output_dir.mkdir(parents=True, exist_ok=True)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    args = (
        f'--outputDirectory "{output_dir}" '
        f'--root "{source_root}" '
        f'--targetFile "{target_file}" '
        f'--targetMethod "{target_method_signature}" '
        f'--jarPath "{jar_dir}"'
    )
    result = subprocess.run(
        [gradle_command, "run", f"--args={args}", "--console=plain"],
        cwd=specimin_dir,
        capture_output=True,
        text=True,
        timeout=600,
    )
    log_path.write_text(
        f"$ {gradle_command} run --args='{args}'\n(cwd={specimin_dir})\n\n"
        f"--- stdout ---\n{result.stdout}\n--- stderr ---\n{result.stderr}\n"
    )

    success = result.returncode == 0 and any(output_dir.rglob("*.java"))
    return SliceResult(snippet_id="", success=success, output_dir=output_dir, log_path=log_path)
