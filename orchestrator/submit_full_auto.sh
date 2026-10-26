#!/bin/bash -l
#SBATCH --job-name=legacy-full-auto
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

# One job, no manual steps in between: regenerates the manifest from the legacy xlsx,
# regenerates the full eligible pool (manifest/included.jsonl) under the current criteria, then
# runs the automatic batching driver (slice -> package -> check per batch, looping until the
# target flagged-finding counts are hit or the pool runs out). Resubmit this same script if it
# times out - every stage it runs is itself resumable/idempotent.

set -euo pipefail
cd "$SLURM_SUBMIT_DIR"

module purge
module load easybuild
module load Java/17.0.15
module load GCCcore/13.3.0
module load Python/3.12.3
source .venv/bin/activate
export PYTHONUNBUFFERED=1

echo "=== Stage: convert (legacy xlsx -> manifest.jsonl) ==="
mkdir -p /project/mjk76/ea442/snippet-selection-pipeline-output/legacy-import/manifest
python3 scripts/convert_legacy_xlsx.py \
  /scratch/mjk76/ea442/final_fixed2.xlsx \
  /project/mjk76/ea442/snippet-selection-pipeline-output/legacy-import/manifest/manifest.jsonl

echo "=== Stage: select (manifest.jsonl -> included.jsonl, full pool, no sampling) ==="
python3 -u -m snippet_pipeline.cli -c ../config/pipeline.yaml --run-id legacy-import select

echo "=== Stage: auto (batch slice/package/check until targets are hit) ==="
python3 -u -m snippet_pipeline.cli -c ../config/pipeline.yaml --run-id legacy-import \
  --batch-size 1000 --min-total-flagged 100 --min-non-nullness-flagged 50 --auto-seed 1 \
  auto

echo "=== Done ==="
