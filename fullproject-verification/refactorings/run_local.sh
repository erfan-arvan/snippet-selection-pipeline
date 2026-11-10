#!/usr/bin/env bash
# Laptop version of submit_check_refactorings.sh (macOS or Linux, no SLURM, no modules).
#
#   bash fullproject-verification/refactorings/run_local.sh [base_dir]        # all cases
#   CASES="row13 row95" bash fullproject-verification/refactorings/run_local.sh
#
# Run from the repo root. Everything goes under base_dir (default ~/fpverify-local):
#   work/      clones of dubbo, netty, hudi, ghidra at the pinned commits (~6 GB once built)
#   m2/        Maven repo, gradle-home/  Gradle cache, apache-maven-3.9.9/  Maven itself
#   results/   results.tsv + per-case logs
# Needs: JDK 21 or newer as `java` (ghidra requires 21; the Maven repos work on 21 too),
#        git, python3, curl, internet. Takes roughly 1-2 hours the first time (downloads).
set -uo pipefail
cd "$(dirname "$0")/../.." || exit 1

JV="$(java -version 2>&1 | grep -Eo 'version "[0-9]+' | grep -Eo '[0-9]+$' || true)"
if [ -z "$JV" ] || [ "$JV" -lt 21 ]; then
  echo "Need JDK >= 21 as 'java' (found '${JV:-none}')." >&2
  echo "  macOS: brew install openjdk@21 && export JAVA_HOME=\$(/usr/libexec/java_home -v 21) && export PATH=\$JAVA_HOME/bin:\$PATH" >&2
  exit 1
fi
for t in git python3 curl; do command -v $t >/dev/null || { echo "missing: $t" >&2; exit 1; }; done

BASE="${1:-$HOME/fpverify-local}"
mkdir -p "$BASE/work" "$BASE/results" "$BASE/m2" "$BASE/gradle-home"
export FPV_WORK="$BASE/work" FPV_OUT="$BASE/results"
export MAVEN_HOME="$BASE/apache-maven-3.9.9"
export M2_REPO="$BASE/m2"
export MAVEN_OPTS="-Dmaven.repo.local=$BASE/m2"
export GRADLE_USER_HOME="$BASE/gradle-home"
unset JAVA_TOOL_OPTIONS 2>/dev/null || true

source fullproject-verification/lib.sh
setup_maven || exit 1
echo "Using: $(java -version 2>&1 | head -1)"
echo "Work dir: $BASE"

rm -f "$FPV_OUT/results.tsv"
CASES="${CASES:-$(grep -v '^#' fullproject-verification/refactorings/cases.tsv | cut -f1 | tr '\n' ' ')}"
FAIL=0
for id in $CASES; do
  bash fullproject-verification/refactorings/check_one.sh "$id" 2>&1 | tee "$FPV_OUT/$id.console.log"
  [ "${PIPESTATUS[0]}" -eq 0 ] || { FAIL=1; echo "case $id: script error (see $FPV_OUT/$id.console.log)" >&2; }
done

echo; echo "===== results ($FPV_OUT/results.tsv) ====="
column -t -s $'\t' "$FPV_OUT/results.tsv" 2>/dev/null || cat "$FPV_OUT/results.tsv"
exit $FAIL
