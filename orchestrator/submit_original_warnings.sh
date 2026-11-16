#!/bin/bash -l
#SBATCH --job-name=original-warnings
#SBATCH --output=%x.%j.out
#SBATCH --error=%x.%j.err
#SBATCH --account=mjk76
#SBATCH --partition=general
#SBATCH --qos=standard
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=128G
#SBATCH --time=3-00:00:00

# Starts from the warnings the checkers ALREADY produced on the original projects, and runs the
# pipeline only on those methods:
#   1. mine: methods with an original-project warning that pass the selection criteria
#      (legacy-import's included.jsonl) and were not sliced before -> candidates.jsonl of a NEW
#      run "original-warnings" (most promising first, at most MAX_METHODS, default 300)
#   2. slice (Specimin) -> package -> check, the pipeline's own stages, on exactly those methods
#   3. compare the slices' warnings with the original warnings (compare_results.py)
# legacy-import and any job running on it are not touched: own run directory, own copy of
# Specimin (two jobs must not run Gradle in the same Specimin folder at once).
#
# Submit from orchestrator/:   sbatch submit_original_warnings.sh
#                              MAX_METHODS=500 sbatch submit_original_warnings.sh
# Resubmitting keeps the method list from the first submit (REGENERATE=1 rebuilds it).
# Results: $RUN/comparison/comparison.csv, comparison_by_slice.csv, comparison.xlsx
#          $RUN/mined/candidates.csv, candidates.txt (every original warning considered)

set -uo pipefail
cd "$SLURM_SUBMIT_DIR"

module purge
module load easybuild
module load Java/17.0.15
module load GCCcore/13.3.0
module load Python/3.12.3
source .venv/bin/activate
export GRADLE_USER_HOME=/scratch/mjk76/ea442/.gradle-home
export PYTHONUNBUFFERED=1

OUTROOT=/project/mjk76/ea442/snippet-selection-pipeline-output
LEGACY=$OUTROOT/legacy-import
RUN=$OUTROOT/original-warnings
step() { echo; echo "[$(date '+%F %T')] === $* ==="; }

# Own Specimin copy + a config that points at it (everything else identical to pipeline.yaml).
SPECIMIN_SRC=/scratch/mjk76/ea442/specimin
SPECIMIN_OWN=/scratch/mjk76/ea442/specimin-original-warnings
CFG=../config/.pipeline-original-warnings.generated.yaml
step "prepare own Specimin copy"
rsync -a "$SPECIMIN_SRC/" "$SPECIMIN_OWN/" || { echo "FATAL: could not copy Specimin" >&2; exit 1; }
sed "s#^\(  specimin_dir:\).*#\1 $SPECIMIN_OWN#" ../config/pipeline.yaml > "$CFG"
grep -q "specimin_dir: $SPECIMIN_OWN" "$CFG" || { echo "FATAL: could not point the config at $SPECIMIN_OWN" >&2; exit 1; }

step "1. mine original-project warnings -> $RUN/manifest/candidates.jsonl"
if [ -s "$RUN/manifest/candidates.jsonl" ] && [ -z "${REGENERATE:-}" ]; then
  echo "keeping existing method list ($(wc -l < "$RUN/manifest/candidates.jsonl") methods); REGENERATE=1 to rebuild"
else
  python3 ../fullproject-verification/mine_original_warnings.py \
    --run "$LEGACY" --write-run "$RUN" --out "$RUN/mined" --max-methods "${MAX_METHODS:-300}" || exit 1
fi
[ -s "$RUN/manifest/candidates.jsonl" ] || { echo "FATAL: no methods to slice" >&2; exit 1; }

PIPE=(python3 -u -m snippet_pipeline.cli -c "$CFG" --run-id original-warnings)
step "2a. slice (Specimin)";  "${PIPE[@]}" slice   || exit 1
step "2b. package";          "${PIPE[@]}" package || exit 1
step "2c. check";            "${PIPE[@]}" check   || exit 1

step "3. compare slice warnings with the original warnings"
python3 ../fullproject-verification/compare_results.py "$RUN" --out "$RUN/comparison/comparison.csv" || exit 1
step "Done. Results in $RUN/comparison/"
