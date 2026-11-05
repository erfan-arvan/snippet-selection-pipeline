#!/bin/bash -l
#SBATCH --job-name=fpverify-hudi
#SBATCH --output=%x.%j.out
#SBATCH --error=%x.%j.err
#SBATCH --account=mjk76
#SBATCH --partition=general
#SBATCH --qos=standard
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=32G
#SBATCH --time=24:00:00

# Full-project checker verification for hudi. UNLIKE the other repos, these patches were
# never validated with a real passing build (we ran out of time budget before confirming) -
# treat the first run of each checker here as the actual first test, not a rerun of something
# already proven. Check fullproject-verification/hudi/README.txt for full detail.
#
# Two known blockers from the sandbox this was prepared in - may or may not apply on HPC:
#   - hudi-utilities needs io.confluent:*:5.5.0 from packages.confluent.io - blocked by the
#     sandbox's proxy. If HPC's network allows that host, unset SKIP_UTILITIES below to include it.
#   - hudi-metaserver needs Docker (or a local thrift 0.13.0 binary) to generate Thrift
#     sources - almost certainly unavailable on HPC compute nodes. Left skipped.

set -uo pipefail
cd "$SLURM_SUBMIT_DIR"

module purge
module load easybuild
module load Java/17.0.15
module load GCCcore/13.3.0
module load Maven/3.9.6 2>/dev/null || module load maven 2>/dev/null || true
if ! command -v mvn >/dev/null 2>&1; then
  echo "FATAL: no 'mvn' on PATH after module load attempts. Load/install Maven 3.9.x before running this." >&2
  exit 1
fi
echo "Using: $(mvn -v | head -1)"

export SKIP_UTILITIES=1
export SKIP_METASERVER=1

WORK=/scratch/mjk76/ea442/fullproject-verify-work/hudi
OUT=/project/mjk76/ea442/snippet-selection-pipeline-output/fullproject-verification/hudi
mkdir -p "$OUT"

if [ -d "$WORK/.git" ] && [ "$(git -C "$WORK" rev-parse HEAD 2>/dev/null)" = "cb32e5e1bac58cbccba8c92c91e7bed4780e9858" ]; then
  echo "hudi already cloned at pinned commit"
else
  rm -rf "$WORK"
  mkdir -p "$WORK"
  git init -q "$WORK"
  git -C "$WORK" remote add origin https://github.com/apache/hudi
  git -C "$WORK" fetch --depth 1 origin cb32e5e1bac58cbccba8c92c91e7bed4780e9858
  git -C "$WORK" checkout -q cb32e5e1bac58cbccba8c92c91e7bed4780e9858
fi

echo "=== prep (one-time: mvn install -DskipTests) ==="
bash fullproject-verification/hudi/run_hudi_checker.sh "$WORK" prep

for c in formatter index nullness regex; do
  echo "=== hudi checker: $c ==="
  bash fullproject-verification/hudi/run_hudi_checker.sh "$WORK" "$c" "$OUT"
done

echo "=== Done. Logs under $OUT ==="
