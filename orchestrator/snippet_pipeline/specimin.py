"""Stage D: invoke Specimin to slice each candidate method into a minimized program.

Important caveat carried over from planning (see README "Limitations"): Specimin's own docs
state its output is "not intended to produce runnable output... only useful for static
analysis" - any non-target method reachable from the target gets its body replaced with
`throw new Error()`. Criterion (1) (all-JDK-types) should mean a target method never calls
back into other project-internal methods, so this normally shouldn't bite, but Stage F's
packaging step still checks for stub bodies as a safety net (see packaging.py).
"""
from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .classpath import ResolvedRepo
from .method_analyzer import MethodRecord


class SourceRootNotFoundError(RuntimeError):
    pass


class SignatureResolutionError(RuntimeError):
    pass


def resolve_method_signature(
    method_analyzer_jar: Path, file_path: Path, simple_class_name: str, method_name: str, num_params: int
) -> tuple[str, list[str]]:
    """Recovers a Specimin-correct (qualifiedClassName, paramTypes) by parsing the method's
    actual source file - never resolving types, just reading them as written - rather than
    trusting the manifest's own qualifiedClassName/paramTypes, which for legacy-imported
    candidates can be wrong in ways that make the manifest's own targetMethodSignature
    unusable: fully-qualified type names Specimin won't match against source, the literal
    "Unresolved" placeholder for types the old tool couldn't resolve, or (independent of either
    of those) a nested class's bare simple name with nothing indicating it's nested.

    Raises SignatureResolutionError if the method can't be found unambiguously in the file -
    never guesses at a signature.
    """
    result = subprocess.run(
        ["java", "-cp", str(method_analyzer_jar), "com.github.erfanarvan.methodanalyzerapp.ResolveMethodSignature",
         str(file_path), simple_class_name, method_name, str(num_params)],
        capture_output=True,
        text=True,
        timeout=60,
    )
    if result.returncode != 0:
        raise SignatureResolutionError(result.stderr.strip())
    data = json.loads(result.stdout)
    return data["qualifiedClassName"], data["paramTypes"]


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


@dataclass
class SliceResult:
    snippet_id: str
    success: bool
    output_dir: Path
    log_path: Path


def slice_candidate(
    specimin_dir: Path,
    source_root: Path,
    target_file: str,
    target_method_signature: str,
    output_dir: Path,
    log_path: Path,
) -> SliceResult:
    output_dir.mkdir(parents=True, exist_ok=True)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    # No --jarPath: per Specimin's own docs and its author's guidance, omitting the classpath
    # makes it fall into approximate mode, synthesizing stand-ins for anything it can't resolve
    # from the source tree alone - this avoids depending on this repo's build system/dependency
    # resolution working at all, which has been the source of most HPC portability trouble.
    args = (
        f'--outputDirectory "{output_dir}" '
        f'--root "{source_root}" '
        f'--targetFile "{target_file}" '
        f'--targetMethod "{target_method_signature}"'
    )
    # Always use Specimin's own bundled wrapper - it ships one, so there's no reason to
    # depend on a system-wide `gradle` (which e.g. an HPC cluster may not have).
    gradlew_path = specimin_dir / "gradlew"
    # Some filesystems (seen on an HPC /project mount) don't reliably preserve git's tracked
    # executable bit on checkout - re-assert it rather than trust that git got it right.
    gradlew_path.chmod(0o755)
    gradlew = str(gradlew_path)
    result = subprocess.run(
        [gradlew, "run", f"--args={args}", "--console=plain"],
        cwd=specimin_dir,
        capture_output=True,
        text=True,
        timeout=600,
    )
    log_path.write_text(
        f"$ {gradlew} run --args='{args}'\n(cwd={specimin_dir})\n\n"
        f"--- stdout ---\n{result.stdout}\n--- stderr ---\n{result.stderr}\n"
    )

    success = result.returncode == 0 and any(output_dir.rglob("*.java"))
    return SliceResult(snippet_id="", success=success, output_dir=output_dir, log_path=log_path)
