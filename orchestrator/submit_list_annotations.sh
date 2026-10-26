#!/bin/bash -l
#SBATCH --job-name=list-annotations
#SBATCH --output=%x.%j.out
#SBATCH --error=%x.%j.err
#SBATCH --partition=general
#SBATCH --qos=standard
#SBATCH --account=mjk76
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --time=00:30:00
#SBATCH --mem-per-cpu=2000M

module purge
module load easybuild
module load GCCcore/13.3.0
module load Python/3.12.3

cd /project/mjk76/ea442/snippet-selection-pipeline/orchestrator
source .venv/bin/activate

python3 scripts/list_annotations.py /scratch/mjk76/ea442/final_fixed2.xlsx
