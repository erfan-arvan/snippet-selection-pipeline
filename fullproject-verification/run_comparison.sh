#!/bin/bash -l
# Compares sliced-snippet checker warnings with the full-project runs. Read-only: it does not
# run the pipeline, Maven, Gradle or any checker. Run from anywhere on a Wulver login node:
#   bash fullproject-verification/run_comparison.sh [run_dir]
# Output: summary on screen + per-row CSV at
#   /project/mjk76/ea442/snippet-selection-pipeline-output/fullproject-verification/comparison.csv
cd "$(dirname "$0")/.." || exit 1
module load easybuild >/dev/null 2>&1
module load Java/23.0.2 >/dev/null 2>&1   # only to parse sources for method line ranges
python3 fullproject-verification/compare_results.py \
  "${1:-/project/mjk76/ea442/snippet-selection-pipeline-output/legacy-import}"
