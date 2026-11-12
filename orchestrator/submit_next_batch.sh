#!/bin/bash -l
#SBATCH --job-name=legacy-next-batch
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

# Runs the NEXT batch(es) of the existing legacy-import auto run: same run id, seed and batch
# size as submit_auto.sh, so it continues from where the last run stopped (the next unprocessed
# methods of the same shuffled pool) - slice (Specimin) -> package -> check.
# The earlier run already met its flagged targets, so --max-batches makes it run anyway.
#
# Submit from orchestrator/:   sbatch submit_next_batch.sh            (one batch = 1000 methods)
#                              BATCHES=2 sbatch submit_next_batch.sh  (two batches)
# Before running, the current stats/ and batch state are copied to stats/backup-<date>/.

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

RUN=/project/mjk76/ea442/snippet-selection-pipeline-output/legacy-import
BK="$RUN/stats/backup-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$BK"
cp -p "$RUN"/stats/*.jsonl "$RUN"/stats/*.csv "$BK"/ 2>/dev/null
cp -p "$RUN/manifest/auto_batch_state.json" "$BK"/ 2>/dev/null
echo "Backed up current results to $BK"
echo "Batch state before: $(cat "$RUN/manifest/auto_batch_state.json" 2>/dev/null)"

python3 -u -m snippet_pipeline.cli -c ../config/pipeline.yaml --run-id legacy-import \
  --batch-size 1000 --min-total-flagged 100 --min-non-nullness-flagged 50 --auto-seed 1 \
  --max-batches "${BATCHES:-1}" \
  auto
rc=$?
echo "Batch state after: $(cat "$RUN/manifest/auto_batch_state.json" 2>/dev/null)"
exit $rc
