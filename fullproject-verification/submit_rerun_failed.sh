#!/bin/bash
# Reruns only the steps that failed in the 2026-11-05 run (jobs 1495478 / 1495480):
#   dubbo index (exclusion fix), ghidra index (heap 7g -> 24g), ghidra nullness (DMG checker-qual,
#   heap). Run from the repo root on a Wulver login node:
#   bash fullproject-verification/submit_rerun_failed.sh
set -e
cd "$(dirname "$0")/.."
ONLY='dubbo: index' sbatch fullproject-verification/submit_verify_light.sh
CHECKERS='index nullness' sbatch fullproject-verification/submit_verify_ghidra.sh
