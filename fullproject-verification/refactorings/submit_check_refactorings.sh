#!/bin/bash -l
#SBATCH --job-name=fpverify-refactor
#SBATCH --output=%x.%j.out
#SBATCH --error=%x.%j.err
#SBATCH --account=mjk76
#SBATCH --partition=general
#SBATCH --qos=standard
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=64G
#SBATCH --time=12:00:00

# Checks whether each refactoring in refactorings/patches makes its checker warning go away.
# For every case in refactorings/cases.tsv: run the checker on the original code (control),
# apply the patch, run it again, and compare the warnings inside the target method.
#
# Submit from the repo root:   sbatch fullproject-verification/refactorings/submit_check_refactorings.sh
# Only some cases:              CASES="row13 row95" sbatch fullproject-verification/refactorings/submit_check_refactorings.sh
# Results: /project/mjk76/ea442/snippet-selection-pipeline-output/fullproject-verification/refactorings/results.tsv
# Uses the clones under /scratch/mjk76/ea442/fullproject-verify-work: don't run it at the same
# time as the other fpverify jobs.

set -uo pipefail
cd "$SLURM_SUBMIT_DIR"
source fullproject-verification/lib.sh
OUT=/project/mjk76/ea442/snippet-selection-pipeline-output/fullproject-verification/refactorings
mkdir -p "$OUT"
rm -f "$OUT/results.tsv"

CASES="${CASES:-$(grep -v '^#' fullproject-verification/refactorings/cases.tsv | cut -f1 | tr '\n' ' ')}"
FAIL=0
for id in $CASES; do
  repo=$(awk -F'\t' -v id="$id" '$1==id{print $2}' fullproject-verification/refactorings/cases.tsv)
  module purge
  module load easybuild
  module load GCCcore/13.3.0
  if [ "$repo" = ghidra ]; then
    module load Java/23.0.2            # ghidra needs JDK >= 21
    export GRADLE_USER_HOME=/scratch/mjk76/ea442/.gradle-home
  else
    module load Java/17.0.15
    setup_maven >/dev/null || exit 1
    if [ "$repo" = hudi ]; then
      export MAVEN_OPTS="-Dmaven.repo.local=/scratch/mjk76/ea442/.m2-fpverify-hudi"
    else
      unset MAVEN_OPTS
      export M2_REPO=/scratch/mjk76/ea442/.m2-fpverify-light
    fi
  fi
  bash fullproject-verification/refactorings/check_one.sh "$id" || { FAIL=1; echo "case $id: script error" >&2; }
done

echo; echo "===== results ($OUT/results.tsv) ====="
column -t -s $'\t' "$OUT/results.tsv" 2>/dev/null || cat "$OUT/results.tsv"
exit $FAIL
