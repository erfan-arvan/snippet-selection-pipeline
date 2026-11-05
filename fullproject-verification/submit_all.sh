#!/bin/bash
# Submits all three full-project verification jobs (they run independently, in parallel).
# Run from the repo root on a Wulver login node:
#   bash fullproject-verification/submit_all.sh
set -e
cd "$(dirname "$0")/.."
sbatch fullproject-verification/submit_verify_light.sh    # apollo, mybatis-3, netty, dubbo
sbatch fullproject-verification/submit_verify_hudi.sh     # hudi
sbatch fullproject-verification/submit_verify_ghidra.sh   # ghidra
echo "Logs: /project/mjk76/ea442/snippet-selection-pipeline-output/fullproject-verification/<repo>/"
echo "Progress: tail -f fpverify-*.<jobid>.out"
