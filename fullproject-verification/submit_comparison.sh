#!/bin/bash -l
#SBATCH --job-name=fpverify-compare
#SBATCH --output=%x.%j.out
#SBATCH --error=%x.%j.err
#SBATCH --account=mjk76
#SBATCH --partition=general
#SBATCH --qos=standard
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=2
#SBATCH --mem=8G
#SBATCH --time=02:00:00

# Sliced vs full-project comparison. Read-only: does not run the pipeline, Maven, Gradle or any
# checker - it reads stats/results.jsonl + snippets/*/snippet.json of the run below, the logs the
# fpverify-light/hudi/ghidra jobs wrote, and the pinned-commit clones (to find method line ranges).
# Submit from the repo root:  sbatch fullproject-verification/submit_comparison.sh
# Summary: fpverify-compare.<jobid>.out
# Per row: /project/mjk76/ea442/snippet-selection-pipeline-output/fullproject-verification/comparison.csv

set -uo pipefail
cd "$SLURM_SUBMIT_DIR"

module purge
module load easybuild
module load Java/23.0.2   # only to parse sources (Locator.java) for method line ranges

RUN_DIR=/project/mjk76/ea442/snippet-selection-pipeline-output/legacy-import
python3 fullproject-verification/compare_results.py "$RUN_DIR"
