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
module load Java/17.0.15
module load GCCcore/13.3.0
module load Gradle/8.9 2>/dev/null || module load gradle 2>/dev/null || true
if ! command -v gradle >/dev/null 2>&1; then
  echo "FATAL: no 'gradle' on PATH after module load attempts. Ghidra needs Gradle >= 8.5 (validated with 8.14.3)." >&2
  exit 1
fi
echo "Using: $(gradle -v | grep -i '^Gradle')"

# Same GRADLE_USER_HOME fix already in use elsewhere in this pipeline - keeps Gradle's
# distribution/dependency cache off the 50GB home quota.
export GRADLE_USER_HOME=/scratch/mjk76/ea442/.gradle-home

WORK=/scratch/mjk76/ea442/fullproject-verify-work/ghidra
OUT=/project/mjk76/ea442/snippet-selection-pipeline-output/fullproject-verification/ghidra
mkdir -p "$OUT"

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
  echo "=== ghidra checker: $c ==="
  bash fullproject-verification/ghidra/run_ghidra_checker.sh --init "$WORK" "$c" "$OUT/$c.log"
done

echo "=== Done. Logs under $OUT ==="
