"""Stage A: per-repo classpath resolution and staging.

For each configured repo, this:
  1. Auto-resolves the repo's dependency jars via its own build tool (gradle/maven), per the
     project decision to prefer accuracy over a shared best-effort jar cache.
  2. Discovers Java source roots (handles common single- and multi-module layouts).
  3. Materializes a *staging* directory containing a symlink to the real repo (never writes
     into the user's actual checkout) plus the two convention files MethodAnalyzerApp reads:
     `.pipeline-classpath.txt` and `.pipeline-sourceroot.txt`.

Known limitation (documented in the README, not silently papered over): classpath
auto-resolution here is generic and best-effort. It unions the compile classpath across every
Gradle/Maven module it finds rather than mapping each candidate file to its owning module's
exact classpath. That's strictly more permissive than the real per-module classpath - it can
occasionally let an ambiguous symbol resolve that a precise per-module classpath would not -
but it never *removes* a jar a module actually needs, so it fails safe with respect to
criterion (1)'s "unresolved => not JDK" rule. Repos with unusual build setups that this can't
resolve at all should use `classpath_override` in pipeline.yaml.

Each target repo's own bundled wrapper (`gradlew`/`mvnw`) is always preferred over
`gradle_command`/`maven_command` when present - those config values are only a fallback for
the rare repo that doesn't ship one, so this works on systems (e.g. an HPC cluster) with no
system-wide `gradle`/`mvn` install at all.

Classpath resolution is best-effort, not required: if a repo has neither its own wrapper nor
a working fallback command (or the build itself fails), this logs a warning and proceeds with
zero extra classpath jars for that repo rather than aborting the whole run. This doesn't loosen
criterion (1) - JDK types resolve via reflection with no jars needed, and same-project types
resolve via the source tree alone - it only means a genuine third-party dependency type can't
be *confirmed* as such, and gets treated as unresolved (which fails criterion (1) anyway, since
it isn't JDK either way). So a repo with no build tooling at all - e.g. a source-only checkout
that was never a full git clone - still gets scanned, just slightly more conservatively.
"""
from __future__ import annotations

import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .config import RepoConfig

_GRADLE_INIT_SCRIPT = """\
allprojects {
    tasks.register("snippetPipelinePrintClasspath") {
        doLast {
            def sourceSets = project.extensions.findByName("sourceSets")
            if (sourceSets != null && sourceSets.findByName("main") != null) {
                sourceSets["main"].compileClasspath.files.each { println it.absolutePath }
            }
        }
    }
}
"""

MAX_MODULE_SEARCH_DEPTH = 6


@dataclass
class ResolvedRepo:
    repo: RepoConfig
    staging_dir: Path
    source_roots: list[Path]
    classpath_jars: list[Path]


def discover_source_roots(repo_path: Path) -> list[Path]:
    """Finds every `src/main/java` under the repo root, up to a bounded depth, so
    multi-module repos (most of the 16 target projects) get all their modules' sources.
    Falls back to the repo root itself if none is found (e.g. a flat/non-conventional layout).
    """
    roots = []
    for candidate in repo_path.glob("*/src/main/java"):
        roots.append(candidate)
    if repo_path.joinpath("src/main/java").is_dir():
        roots.append(repo_path / "src/main/java")
    # Deeper modules, e.g. kafka/streams/src/main/java, dubbo/dubbo-common/src/main/java
    for depth in range(2, MAX_MODULE_SEARCH_DEPTH):
        pattern = "/".join(["*"] * depth) + "/src/main/java"
        for candidate in repo_path.glob(pattern):
            if "/test/" not in str(candidate) and "build" not in candidate.parts:
                roots.append(candidate)
    roots = sorted(set(roots))
    return roots or [repo_path]


def _gradle_executable(repo_path: Path, fallback_command: str) -> str:
    """Prefers the target repo's own bundled wrapper (virtually universal for real-world
    Gradle projects, and the only thing guaranteed to work on a system with no system-wide
    `gradle` - e.g. an HPC cluster with only a Java module) over a configurable fallback.
    """
    wrapper = repo_path / "gradlew"
    if wrapper.is_file():
        # Some filesystems (seen on an HPC /project mount) don't reliably preserve git's
        # tracked executable bit on checkout - re-assert it rather than trust the checkout.
        wrapper.chmod(0o755)
        return str(wrapper)
    return fallback_command


def _maven_executable(repo_path: Path, fallback_command: str) -> str:
    wrapper = repo_path / "mvnw"
    if wrapper.is_file():
        wrapper.chmod(0o755)
        return str(wrapper)
    return fallback_command


_DEGRADED_CLASSPATH_NOTE = (
    "proceeding with zero extra classpath jars for this repo. This only makes criterion (1) "
    "more conservative, not less correct: JDK types still resolve fine (reflection needs no "
    "jars) and same-project types still resolve fine (needs only the source tree, already "
    "present) - the only thing this can miss is confirming a genuine third-party type, which "
    "would fail criterion (1) anyway once confirmed, so the end result is rarely different."
)


def resolve_classpath_gradle(repo_path: Path, gradle_command: str) -> list[Path]:
    gradle = _gradle_executable(repo_path, gradle_command)
    with tempfile.NamedTemporaryFile("w", suffix=".init.gradle", delete=False) as f:
        f.write(_GRADLE_INIT_SCRIPT)
        init_script = f.name
    try:
        try:
            result = subprocess.run(
                [gradle, "--init-script", init_script, "-q", "snippetPipelinePrintClasspath"],
                cwd=repo_path,
                capture_output=True,
                text=True,
                timeout=1800,
            )
        except (FileNotFoundError, PermissionError) as e:
            print(f"WARNING: no working gradle for {repo_path} (tried '{gradle}': {e}); {_DEGRADED_CLASSPATH_NOTE}")
            return []

        if result.returncode != 0:
            print(
                f"WARNING: gradle classpath resolution failed for {repo_path} (exit {result.returncode}); "
                f"{_DEGRADED_CLASSPATH_NOTE}\n{result.stderr[-2000:]}"
            )
            return []
        return [Path(line.strip()) for line in result.stdout.splitlines() if line.strip()]
    finally:
        Path(init_script).unlink(missing_ok=True)


def resolve_classpath_maven(repo_path: Path, maven_command: str) -> list[Path]:
    maven = _maven_executable(repo_path, maven_command)
    jars: set[Path] = set()
    # Union across every module's pom.xml, since a candidate method can live in any module.
    for pom in repo_path.glob("**/pom.xml"):
        module_dir = pom.parent
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            out_file = f.name
        try:
            try:
                result = subprocess.run(
                    [maven, "-q", "-DincludeScope=compile", f"-Dmdep.outputFile={out_file}", "dependency:build-classpath"],
                    cwd=module_dir,
                    capture_output=True,
                    text=True,
                    timeout=1800,
                )
            except (FileNotFoundError, PermissionError) as e:
                print(f"WARNING: no working maven for {module_dir} (tried '{maven}': {e}); {_DEGRADED_CLASSPATH_NOTE}")
                continue  # best-effort across modules; a failing module just contributes no jars
            if result.returncode != 0:
                continue  # best-effort across modules; a failing module just contributes no jars
            content = Path(out_file).read_text().strip()
            if content:
                jars.update(Path(p) for p in content.split(":") if p)
        finally:
            Path(out_file).unlink(missing_ok=True)
    return sorted(jars)


def resolve_classpath(repo: RepoConfig, gradle_command: str, maven_command: str) -> list[Path]:
    if repo.classpath_override:
        override_path = Path(repo.classpath_override).expanduser().resolve()
        return [Path(line.strip()) for line in override_path.read_text().splitlines() if line.strip()]

    repo_path = repo.resolved_path()
    if repo.build_system == "gradle":
        return resolve_classpath_gradle(repo_path, gradle_command)
    elif repo.build_system == "maven":
        return resolve_classpath_maven(repo_path, maven_command)
    else:
        raise ValueError(f"Unknown build_system '{repo.build_system}' for repo '{repo.name}'")


def stage_repo(repo: RepoConfig, staging_root: Path, gradle_command: str, maven_command: str) -> ResolvedRepo:
    """Builds the staging directory MethodAnalyzerApp will treat as one "project": a symlink
    to the real repo plus the two convention files, so nothing is ever written into the
    user's actual checkout.
    """
    repo_path = repo.resolved_path()
    staging_dir = staging_root / repo.name
    staging_dir.mkdir(parents=True, exist_ok=True)

    source_link = staging_dir / "source"
    if not source_link.exists():
        source_link.symlink_to(repo_path, target_is_directory=True)

    source_roots = [source_link / p.relative_to(repo_path) for p in discover_source_roots(repo_path)]
    classpath_jars = resolve_classpath(repo, gradle_command, maven_command)

    (staging_dir / ".pipeline-sourceroot.txt").write_text(
        "\n".join(str(p) for p in source_roots) + "\n"
    )
    (staging_dir / ".pipeline-classpath.txt").write_text(
        "\n".join(str(p) for p in classpath_jars) + "\n"
    )

    return ResolvedRepo(repo=repo, staging_dir=staging_dir, source_roots=source_roots, classpath_jars=classpath_jars)


def stage_all_repos(repos: list[RepoConfig], staging_root: Path, gradle_command: str, maven_command: str) -> list[ResolvedRepo]:
    staging_root.mkdir(parents=True, exist_ok=True)
    return [stage_repo(repo, staging_root, gradle_command, maven_command) for repo in repos]
