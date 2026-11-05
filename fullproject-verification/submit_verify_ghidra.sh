#!/bin/bash -l
#SBATCH --job-name=fpverify-ghidra
#SBATCH --output=%x.%j.out
#SBATCH --error=%x.%j.err
#SBATCH --account=mjk76
#SBATCH --partition=general
#SBATCH --qos=standard
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=64G
#SBATCH --time=72:00:00

# Full-project checker verification for ghidra - the hardest repo in this set. Only 2 of its
# 5 checkers (regex, resourceleak) were actually validated with a passing build before we ran
# out of time budget; index/nullness/interning patches exist but were never run. Check
# fullproject-verification/ghidra/README.md for the full list of gotchas (dependency-fetch
# init step, -nowarn override, Gradle UP-TO-DATE caching trap, DMG's nonstandard task name).
#
# 72h timewall per this project's standing convention for HPC jobs.

set -uo pipefail
cd "$SLURM_SUBMIT_DIR"
source fullproject-verification/lib.sh

module purge
module load easybuild
module load GCCcore/13.3.0

# Ghidra needs JDK >= 21 (application.java.min=21) - NOT the JDK 17 the rest of this
# pipeline uses for the Checker Framework itself. Confirmed via `module avail Java` on
# Wulver: only Java/17.0.15 and Java/23.0.2 exist there, so use the latter.
module load "${JAVA_MODULE:-Java/23.0.2}"
JV="$(java -version 2>&1 | grep -Eo 'version "[0-9]+' | grep -Eo '[0-9]+$' || true)"
if [ -z "$JV" ] || [ "$JV" -lt 21 ]; then
  echo "FATAL: need a JDK >= 21 on PATH for ghidra (found '${JV:-none}')." >&2
  echo "  Run 'module avail Java' to find the exact name, then: JAVA_MODULE=<name> sbatch fullproject-verification/submit_verify_ghidra.sh" >&2
  exit 1
fi
echo "Using: $(java -version 2>&1 | head -1)"

# No system-wide Gradle module needed: run_ghidra_checker.sh uses ghidra's own bundled
# ./gradlew by default (same convention as the rest of this pipeline - see
# orchestrator/snippet_pipeline/classpath.py). Set GRADLE=/path/to/gradle to override.

# Same GRADLE_USER_HOME fix already in use elsewhere in this pipeline - keeps Gradle's
# distribution/dependency cache off the 50GB home quota.
export GRADLE_USER_HOME=/scratch/mjk76/ea442/.gradle-home

# Type-check only the ghidra classes that have flagged rows (see lib.sh only_defs_regex).
export ONLY_DEFS="$(only_defs_regex ghidra)"
[ -n "$ONLY_DEFS" ] || { echo "FATAL: no flagged ghidra classes found in results.jsonl" >&2; exit 1; }
echo "Checking only: $ONLY_DEFS"

WORK=/scratch/mjk76/ea442/fullproject-verify-work/ghidra
OUT=/project/mjk76/ea442/snippet-selection-pipeline-output/fullproject-verification/ghidra
mkdir -p "$OUT"

# Timestamped step banner - tail -f fpverify-ghidra.<jobid>.out to watch progress; this is the
# 72h job, so this is the main way to tell "still compiling" from "stuck". run_ghidra_checker.sh
# now streams gradle's live output here too (via tee), not just into its own log file.
step() { echo; echo "[$(date '+%Y-%m-%d %H:%M:%S')] === $* ==="; }

GHIDRA_URL=https://github.com/NationalSecurityAgency/ghidra
GHIDRA_COMMIT=93c19e3cc6733fab119ace63a39be2aec89208b3

FAIL=0
FAILED_STEPS=()
# CHECKERS="index nullness" sbatch ... reruns just those checkers (default: all five).
for c in ${CHECKERS:-regex resourceleak interning index nullness}; do
  step "ghidra checker: $c"
  # Every checker starts from a clean tree at the pinned commit (reuses the clone; only
  # discards leftovers, e.g. a build.gradle patch not reverted because a job was killed).
  if ! prepare_clone "$GHIDRA_URL" "$GHIDRA_COMMIT" "$WORK"; then
    FAIL=1; FAILED_STEPS+=("$c (clone not clean)"); continue
  fi
  bash fullproject-verification/ghidra/run_ghidra_checker.sh --init "$WORK" "$c" "$OUT/$c.log"
  rc=$?
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] --- ghidra $c exit=$rc"
  if [ $rc -ne 0 ]; then FAIL=1; FAILED_STEPS+=("$c (exit $rc)"); fi
done

step "Done. Logs under $OUT"
if [ ${#FAILED_STEPS[@]} -gt 0 ]; then
  echo "Steps with non-zero exit:"
  printf '  %s\n' "${FAILED_STEPS[@]}"
fi
exit $FAIL
