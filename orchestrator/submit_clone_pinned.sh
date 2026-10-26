#!/bin/bash -l
#SBATCH --job-name=clone-repos-pinned
#SBATCH --output=%x.%j.out
#SBATCH --error=%x.%j.err
#SBATCH --account=mjk76
#SBATCH --partition=general
#SBATCH --qos=standard
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --time=3-00:00:00
#SBATCH --mem-per-cpu=2000M

module purge
module load easybuild
module load GCCcore/13.3.0
module load Python/3.12.3

cd /project/mjk76/ea442/snippet-selection-pipeline/orchestrator
source .venv/bin/activate

mkdir -p /scratch/mjk76/ea442/repos-pinned
python3 scripts/clone_repos_at_pinned_commits.py \
  ../config/pipeline.yaml /scratch/mjk76/ea442/repos-pinned
