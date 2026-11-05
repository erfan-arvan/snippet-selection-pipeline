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

module purge
module load easybuild
module load GCCcore/13.3.0

# Ghidra needs JDK >= 21 (application.java.min=21) - NOT the JDK 17 the rest of this
# pipeline uses for the Checker Framework itself. The exact module name/version varies
# by site, so this tries a few plausible easybuild names, then hard-verifies the result
# rather than trusting any one of them blindly. If all of these miss, run
# `module avail Java` yourself and re-submit with: JAVA_MODULE=<exact name> sbatch ...
for m in "${JAVA_MODULE:-}" Java/21.0.5 Java/21.0.2 Java/21 Java/22.0.1 Java/22; do
  [ -z "$m" ] && continue
  module load "$m" 2>/dev/null && { echo "Loaded Java module: $m"; break; }
done
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

WORK=/scratch/mjk76/ea442/fullproject-verify-work/ghidra
OUT=/project/mjk76/ea442/snippet-selection-pipeline-output/fullproject-verification/ghidra
mkdir -p "$OUT"

# Timestamped step banner - tail -f fpverify-ghidra.<jobid>.out to watch progress; this is the
# 72h job, so this is the main way to tell "still compiling" from "stuck". run_ghidra_checker.sh
# now streams gradle's live output here too (via tee), not just into its own log file.
step() { echo; echo "[$(date '+%Y-%m-%d %H:%M:%S')] === $* ==="; }

if [ -d "$WORK/.git" ] && [ "$(git -C "$WORK" rev-parse HEAD 2>/dev/null)" = "93c19e3cc6733fab119ace63a39be2aec89208b3" ]; then
  echo "ghidra already cloned at pinned commit"
else
  rm -rf "$WORK"
  mkdir -p "$WORK"
  git init -q "$WORK"
  git -C "$WORK" remote add origin https://github.com/NationalSecurityAgency/ghidra
  git -C "$WORK" fetch --depth 1 origin 93c19e3cc6733fab119ace63a39be2aec89208b3
  git -C "$WORK" checkout -q 93c19e3cc6733fab119ace63a39be2aec89208b3
fi

for c in index interning nullness regex resourceleak; do
  step "ghidra checker: $c"
  bash fullproject-verification/ghidra/run_ghidra_checker.sh --init "$WORK" "$c" "$OUT/$c.log"
done

step "Done. Logs under $OUT"
