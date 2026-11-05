#!/usr/bin/env bash
# =============================================================================
# run_ghidra_checker.sh -- run ONE Checker Framework checker against the REAL
# ghidra modules that contain our target classes, through ghidra's own Gradle
# build, then revert the build-file patch.
#
# usage:
#   run_ghidra_checker.sh [--init] [--force-init] <ghidra_clone_dir> <checker_id> [log_file]
#
#   checker_id   one of: index interning nullness regex resourceleak
#   --init       run ghidra's dependency-fetch step if dependencies/flatRepo is
#                missing (this is the default; the flag is for clarity)
#   --force-init re-run the dependency-fetch step even if it looks complete
#   --init-only  only do initialization (e.g. on a login node with network),
#                then exit without building
#
# env:
#   GRADLE            gradle executable (default: the clone's own ./gradlew wrapper;
#                     ghidra needs Gradle >= 8.5; validated with 8.14.3)
#   GRADLE_USER_HOME  RESPECTED if already set (e.g. by your HPC module setup).
#                     If unset, defaults to <clone>/../ghidra_gradle_user_home.
#   GRADLE_OFFLINE=1  pass --offline to the build (cache must be warm already)
#
# The pinned commit for this re-audit is 93c19e3cc6733fab119ace63a39be2aec89208b3.
# Clone it with:
#   git init ghidra && cd ghidra
#   git remote add origin https://github.com/NationalSecurityAgency/ghidra
#   git fetch --depth 1 origin 93c19e3cc6733fab119ace63a39be2aec89208b3
#   git checkout FETCH_HEAD
# =============================================================================
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PINNED=93c19e3cc6733fab119ace63a39be2aec89208b3
FORCE_INIT=0; INIT_ONLY=0
while [[ $# -gt 0 && "$1" == --* ]]; do
  case "$1" in
    --init) ;;
    --force-init) FORCE_INIT=1 ;;
    --init-only) INIT_ONLY=1 ;;
    *) echo "unknown flag $1" >&2; exit 2 ;;
  esac
  shift
done
if [[ $# -lt 1 || ( $INIT_ONLY -eq 0 && $# -lt 2 ) ]]; then
  sed -n '2,30p' "$0"; exit 2
fi
G="$(cd "$1" && pwd)" || exit 2
CHECKER="${2:-}"
LOG="${3:-$PWD/ghidra_${CHECKER:-init}_build.log}"
# Use ghidra's own bundled wrapper by default, same convention as the rest of this
# pipeline (classpath.py/config.py) - never depend on a system-wide `gradle` module
# on HPC. Set GRADLE=... to force a specific/system gradle instead.
GRADLE="${GRADLE:-$G/gradlew}"
[[ "$GRADLE" == "$G/gradlew" ]] && chmod +x "$GRADLE"

die() { echo "ERROR: $*" >&2; exit 1; }

# ---------------------------------------------------------------- sanity
[[ -f "$G/Ghidra/application.properties" && -f "$G/settings.gradle" ]] || die "$G is not a ghidra clone"
HEAD_SHA="$(git -C "$G" rev-parse HEAD 2>/dev/null)"
[[ "$HEAD_SHA" == "$PINNED" ]] || echo "WARNING: clone HEAD is $HEAD_SHA, expected pinned $PINNED" >&2

if [[ -z "${GRADLE_USER_HOME:-}" ]]; then
  export GRADLE_USER_HOME="$(dirname "$G")/ghidra_gradle_user_home"
  echo "GRADLE_USER_HOME was unset -> using $GRADLE_USER_HOME"
else
  echo "Using existing GRADLE_USER_HOME=$GRADLE_USER_HOME"
fi
mkdir -p "$GRADLE_USER_HOME"

JV="$(java -version 2>&1 | grep -Eo 'version "[0-9]+' | grep -Eo '[0-9]+$')"
[[ -n "$JV" && "$JV" -ge 21 ]] || die "ghidra 11.4-DEV needs JDK >= 21 (application.java.min=21); found '${JV:-none}'. module load / set JAVA_HOME first."
command -v "$GRADLE" >/dev/null || die "gradle not found (set GRADLE=/path/to/gradle; need >= 8.5)"

# ---------------------------------------------------------------- init
# Ghidra's documented first step (DevGuide.md "Common Gradle Tasks"):
#     gradle -I gradle/support/fetchDependencies.gradle
# It downloads non-Maven-Central artifacts into dependencies/downloads and
# builds dependencies/flatRepo (java-sarif-2.1-modified.jar, AXMLPrinter2.jar),
# which the module build.gradles resolve via flatDir. Skipping it gives
# "Unable to find the local maven repo. Ensure you have created the flatRepo
#  directory or ghidra.repos.config file."
need_init() {
  [[ $FORCE_INIT -eq 1 ]] && return 0
  [[ -f "$G/dependencies/flatRepo/java-sarif-2.1-modified.jar" && -f "$G/dependencies/flatRepo/AXMLPrinter2.jar" ]] && return 1
  return 0
}

fallback_predownload() {
  # Some networks/proxies block https://github.com/<org>/<repo>/raw/... (but not
  # raw.githubusercontent.com) and/or ftp.postgresql.org / archive.eclipse.org.
  # Pre-download with curl into dependencies/downloads (the script skips any
  # file whose sha256 already matches), rewriting github.com/raw URLs.
  # Prints the names of artifacts that still could not be fetched.
  mkdir -p "$G/dependencies/downloads"
  python3 -I - "$G" <<'PY'
import re, subprocess, hashlib, os, sys
G = sys.argv[1]
ver = re.search(r'application\.version=(\S+)', open(G + '/Ghidra/application.properties').read()).group(1)
s = open(G + '/gradle/support/fetchDependencies.gradle').read()
for m in re.finditer(r'name:\s*"([^"]+)",\s*url:\s*"([^"]+)",\s*sha256:\s*"([0-9a-f]+)"', s):
    name, url, sha = m.groups()
    url = url.replace('${RELEASE_VERSION}', ver).replace(
        'https://github.com/NationalSecurityAgency/ghidra-data/raw/',
        'https://raw.githubusercontent.com/NationalSecurityAgency/ghidra-data/')
    out = os.path.join(G, 'dependencies/downloads', name)
    h = lambda: hashlib.sha256(open(out, 'rb').read()).hexdigest() if os.path.exists(out) else None
    if h() == sha:
        continue
    subprocess.run(['curl', '-sS', '-L', '--retry', '3', '-o', out, url])
    if h() != sha:
        if os.path.exists(out): os.remove(out)
        print(name)
PY
}

run_init() {
  echo "== init: official fetchDependencies step"
  ( cd "$G" && "$GRADLE" --no-daemon -I gradle/support/fetchDependencies.gradle ) 2>&1 | tee "$LOG.init"
  [[ ${PIPESTATUS[0]} -eq 0 ]] && { echo "   ok"; return 0; }
  echo "   official fetch failed (see $LOG.init); trying curl pre-download fallback"
  mapfile -t MISSING < <(fallback_predownload)
  local script=gradle/support/fetchDependencies.gradle
  if [[ ${#MISSING[@]} -gt 0 ]]; then
    echo "   could not fetch: ${MISSING[*]}"
    echo "   generating untracked gradle/support/fetchDependencies_local.gradle without them"
    echo "   (only OK if they are not Java compile inputs: postgresql = BSim native"
    echo "    PostgreSQL extension source, cdt = GhidraDev Eclipse plugin)"
    python3 -I - "$G" "${MISSING[@]}" <<'PY'
import sys
G, missing = sys.argv[1], sys.argv[2:]
s = open(G + '/gradle/support/fetchDependencies.gradle').read()
for n in missing:
    i = s.index('name: "%s"' % n); a = s.rindex('[', 0, i); b = s.index('],', i) + 2
    s = s[:a] + s[b:]
# must live in gradle/support/: the script derives REPO_DIR from its own location
open(G + '/gradle/support/fetchDependencies_local.gradle', 'w').write(s)
PY
    script=gradle/support/fetchDependencies_local.gradle
  fi
  ( cd "$G" && "$GRADLE" --no-daemon -I "$script" ) 2>&1 | tee -a "$LOG.init"
  [[ ${PIPESTATUS[0]} -eq 0 ]] || die "fetchDependencies failed even after fallback; see $LOG.init"
  echo "   ok (via $script)"
}

if need_init; then run_init; else echo "== init: dependencies/flatRepo already present, skipping"; fi
[[ -f "$G/dependencies/flatRepo/java-sarif-2.1-modified.jar" ]] || die "flatRepo still missing after init"
[[ $INIT_ONLY -eq 1 ]] && { echo "init-only done"; exit 0; }

# ---------------------------------------------------------------- patch
PATCH="$HERE/patches/$CHECKER.patch"; TASKFILE="$HERE/patches/$CHECKER.tasks"
[[ -f "$PATCH" && -f "$TASKFILE" ]] || die "no patch for checker '$CHECKER' (expected $PATCH)"
git -C "$G" diff --quiet || die "tracked files in $G are modified; refusing to patch (git -C $G checkout -- . to reset)"
git -C "$G" apply --check "$PATCH" || die "patch does not apply cleanly to $G"
mapfile -t PATCHED < <(grep '^+++ b/' "$PATCH" | sed 's#^+++ b/##')
revert() { git -C "$G" checkout -- "${PATCHED[@]}" && echo "== reverted ${#PATCHED[@]} build.gradle file(s)"; }
trap revert EXIT
git -C "$G" apply "$PATCH"
echo "== applied $CHECKER patch to: ${PATCHED[*]}"
# ONLY_DEFS=<regex>: type-check only the matching classes (-AonlyDefs); everything is still compiled.
if [[ -n "${ONLY_DEFS:-}" ]]; then
  for f in "${PATCHED[@]}"; do
    python3 -I - "$G/$f" "$ONLY_DEFS" <<'PY'
import sys
p, rx = sys.argv[1], sys.argv[2]
s = open(p).read()
assert "'-Awarns'" in s, p
open(p, "w").write(s.replace("'-Awarns'", "'-Awarns', '-AonlyDefs=" + rx + "'"))
PY
  done
  echo "== -AonlyDefs=$ONLY_DEFS"
fi

# ---------------------------------------------------------------- build
read -r -a T0 < "$TASKFILE"
# `--rerun` (Gradle >= 7.6) forces each target compile task to execute even if
# it is UP-TO-DATE from an earlier run; an UP-TO-DATE task prints NO
# diagnostics, which would otherwise look like "no warning" (= false artifact).
TASKS=(); for t in "${T0[@]}"; do TASKS+=("$t" --rerun); done
OFF=(); [[ "${GRADLE_OFFLINE:-0}" == 1 ]] && OFF=(--offline)
build() {
  ( cd "$G" && "$GRADLE" --no-daemon --continue "-Dorg.gradle.jvmargs=-Xmx8G -Duser.language=en -Duser.country=US" \
      ${OFF[@]+"${OFF[@]}"} "${TASKS[@]}" ) 2>&1 | tee "$LOG"
  return "${PIPESTATUS[0]}"
}
echo "== gradle ${TASKS[*]}  (log: $LOG)"
build; RC=$?
# Maven Central sometimes answers HTTP 429 (Too Many Requests) on a cold cache.
for i in 1 2 3; do
  grep -q 'status code 429' "$LOG" || break
  echo "   HTTP 429 from Maven Central; retry $i after 60s"; sleep 60; build; RC=$?
done
echo "gradle exit=$RC" >> "$LOG"
NW=$(grep -cE '\.java:[0-9]+: warning: \[' "$LOG")
echo "== gradle exit=$RC; checker diagnostics in log: $NW"
grep -E 'FAILED|What went wrong' -A3 "$LOG" | head -20
exit $RC
