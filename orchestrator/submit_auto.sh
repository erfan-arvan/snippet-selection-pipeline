#!/bin/bash -l
#SBATCH --job-name=legacy-auto
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

set -uo pipefail
cd "$SLURM_SUBMIT_DIR"

module purge
module load easybuild
module load Java/17.0.15
module load GCCcore/13.3.0
module load Python/3.12.3
source .venv/bin/activate

# Gradle caches its distributions/dependency cache in ~/.gradle by default - with dozens of
# repos each pinning a different Gradle version, that fills a 50GB home quota fast (it already
# has once). Redirect it to /scratch instead, which has real headroom.
export GRADLE_USER_HOME=/scratch/mjk76/ea442/.gradle-home

export PYTHONUNBUFFERED=1

python3 -u -m snippet_pipeline.cli -c ../config/pipeline.yaml --run-id legacy-import \
  --batch-size 1000 --min-total-flagged 100 --min-non-nullness-flagged 50 --auto-seed 1 \
  auto
