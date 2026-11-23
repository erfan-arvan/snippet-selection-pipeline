#!/bin/bash -l
#SBATCH --job-name=refactor-slices
#SBATCH --output=%x.%j.out
#SBATCH --error=%x.%j.err
#SBATCH --account=mjk76
#SBATCH --partition=general
#SBATCH --qos=standard
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=32G
#SBATCH --time=04:00:00

# Checks the refactorings on the ALREADY SLICED snippets of the original-warnings run
# (no slicing, no full-project build). For each case: checker on the slice as it is, on the
# slice with the refactoring, and on the refactored slice plus a canary line.
# The slices under original-warnings/snippets are copied, never modified.
#
# Submit from the repo root:
#   CASES="ow34 ow89" sbatch fullproject-verification/refactorings/submit_check_slices.sh
# Slices of other runs: RUNS="<run dir>,<run dir>" (default: the original-warnings run); results folder: OUT=<dir>
# Results: /project/mjk76/ea442/snippet-selection-pipeline-output/original-warnings/refactorings/results.tsv

set -uo pipefail
cd "$SLURM_SUBMIT_DIR"
module purge
module load easybuild
module load Java/17.0.15
module load GCCcore/13.3.0
module load Python/3.12.3
export GRADLE_USER_HOME=/scratch/mjk76/ea442/.gradle-home
export PYTHONUNBUFFERED=1
[ -n "${CASES:-}" ] || { echo "set CASES, e.g. CASES=\"ow34 ow89\"" >&2; exit 2; }
OUT="${OUT:-/project/mjk76/ea442/snippet-selection-pipeline-output/original-warnings/refactorings}"
python3 fullproject-verification/refactorings/check_slices.py ${RUNS:+--run "$RUNS"} --out "$OUT" $CASES
RES=$OUT/results.tsv
echo; echo "===== results ($RES) ====="
column -t -s $'\t' "$RES" 2>/dev/null || cat "$RES"
