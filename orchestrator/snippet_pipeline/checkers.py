"""Stage F: run each configured Checker Framework checker against each packaged snippet,
in isolation (one checker per invocation, never combined), and classify diagnostics as
"on the target method" or "elsewhere in the slice".

Every raw run is persisted to its own log file (see `log_path` on `CheckerRunResult`) - the
stats stage carries that path alongside the parsed result so a flagged/suspect row is always
traceable back to the exact run that produced it, per the explicit requirement that checker
logs be kept and referenced from the printed stats.
"""
from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from .config import CheckerSpec

_DIAGNOSTIC_RE = re.compile(
    r"^(?P<file>.+\.java):(?P<line>\d+):\s*(?P<severity>error|warning):\s*"
    r"(?:\[(?P<key>[\w.]+)\]\s*)?(?P<message>.*)$"
)


@dataclass
class Diagnostic:
    file: str
    line: int
    severity: str
    key: str | None
    message: str
    on_target: bool


@dataclass
class CheckerRunResult:
    snippet_id: str
    checker_id: str
    status: str  # "passed" | "flagged" | "slice_suspect" | "run_error"
    on_target_count: int
    elsewhere_count: int
    diagnostics: list[Diagnostic]
    log_path: Path
    returncode: int


def parse_diagnostics(compiler_output: str) -> list[dict]:
    """Extracts one entry per diagnostic *header* line (file:line: error/warning: [key] msg).
    Continuation lines (source snippet, caret, "N errors") are left in the raw log but not
    modeled individually here - they're not needed to classify or count diagnostics.
    """
    diagnostics = []
    for line in compiler_output.splitlines():
        match = _DIAGNOSTIC_RE.match(line.strip())
        if match:
            diagnostics.append(match.groupdict())
    return diagnostics


def classify_diagnostics(raw_diagnostics: list[dict], sliced_file_suffix: str, start_line: int, end_line: int) -> list[Diagnostic]:
    normalized_suffix = sliced_file_suffix.replace("\\", "/")
    result = []
    for d in raw_diagnostics:
        file_normalized = d["file"].replace("\\", "/")
        line_num = int(d["line"])
        on_target = file_normalized.endswith(normalized_suffix) and start_line <= line_num <= end_line
        result.append(Diagnostic(
            file=d["file"],
            line=line_num,
            severity=d["severity"],
            key=d.get("key"),
            message=d["message"],
            on_target=on_target,
        ))
    return result


def status_for(diagnostics: list[Diagnostic]) -> str:
    if not diagnostics:
        return "passed"
    if any(d.on_target for d in diagnostics):
        return "flagged"
    return "slice_suspect"


def run_checker_on_snippet(
    snippet_dir: Path,
    metadata: dict,
    checker: CheckerSpec,
    log_path: Path,
) -> CheckerRunResult:
    log_path.parent.mkdir(parents=True, exist_ok=True)

    # Always the snippet's own vendored wrapper (see packaging.vendor_gradle_wrapper) - never
    # a system-wide `gradle`, which e.g. an HPC cluster may not have.
    gradlew = str(snippet_dir / "gradlew")
    result = subprocess.run(
        [gradlew, "clean", "compileJava", f"-PcheckerClass={checker.processor}", "--console=plain"],
        cwd=snippet_dir,
        capture_output=True,
        text=True,
        timeout=900,
    )
    combined_output = (
        f"$ {gradlew} clean compileJava -PcheckerClass={checker.processor}\n"
        f"(cwd={snippet_dir})\n\n--- stdout ---\n{result.stdout}\n--- stderr ---\n{result.stderr}\n"
    )
    log_path.write_text(combined_output)

    raw_diagnostics = parse_diagnostics(result.stdout + "\n" + result.stderr)
    diagnostics = classify_diagnostics(
        raw_diagnostics,
        metadata["sliced_file"],
        metadata["sliced_start_line"],
        metadata["sliced_end_line"],
    )

    on_target_count = sum(1 for d in diagnostics if d.on_target)
    elsewhere_count = len(diagnostics) - on_target_count
    status = status_for(diagnostics)

    # A checker run that fails for a reason other than reporting diagnostics (e.g. the
    # snippet doesn't compile at all under plain javac) is its own bucket - it's not the
    # false-positive/true-positive question Stage F exists to answer.
    if result.returncode != 0 and not diagnostics:
        status = "run_error"

    return CheckerRunResult(
        snippet_id=metadata["snippet_id"],
        checker_id=checker.id,
        status=status,
        on_target_count=on_target_count,
        elsewhere_count=elsewhere_count,
        diagnostics=diagnostics,
        log_path=log_path,
        returncode=result.returncode,
    )


def run_checkers_on_snippet(
    snippet_dir: Path,
    checkers: list[CheckerSpec],
    logs_root: Path,
) -> list[CheckerRunResult]:
    metadata = json.loads((snippet_dir / "snippet.json").read_text())
    snippet_id = metadata["snippet_id"]
    results = []
    for checker in checkers:
        log_path = logs_root / snippet_id / f"{checker.id}.log"
        results.append(run_checker_on_snippet(snippet_dir, metadata, checker, log_path))
    return results
