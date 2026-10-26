#!/bin/bash -l
#SBATCH --job-name=legacy-slice
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

set -euo pipefail
cd "$SLURM_SUBMIT_DIR"

module purge
module load easybuild
module load Java/17.0.15
module load GCCcore/13.3.0
module load Python/3.12.3

source .venv/bin/activate

export PYTHONUNBUFFERED=1
python3 -u -m snippet_pipeline.cli -c ../config/pipeline.yaml --run-id legacy-import slice
