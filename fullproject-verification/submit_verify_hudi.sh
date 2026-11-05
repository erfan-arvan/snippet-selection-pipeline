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

# Full-project checker verification for hudi.
# Submit from the repo root:  sbatch fullproject-verification/submit_verify_hudi.sh
#
# Order matters:
#   1. formatter, regex, index, nullness on every target module EXCEPT hudi-utilities.
#      These only need Maven Central.
#   2. LAST, as a separate optional step: `prep` (mvn install, no checker) and then nullness on
#      hudi-utilities alone. That module needs io.confluent artifacts from packages.confluent.io
#      and builds Spark/Scala modules, so it is the step most likely to fail - and if it does,
#      everything in step 1 has already finished and been logged.
# hudi-metaserver-server (needs Docker for its thrift sources) stays skipped.
# See fullproject-verification/hudi/README.txt for the details.

set -uo pipefail
cd "$SLURM_SUBMIT_DIR"
source fullproject-verification/lib.sh

module purge
module load easybuild
module load Java/17.0.15
module load GCCcore/13.3.0

# hudi has no ./mvnw: use the shared Maven 3.9.9 (see lib.sh setup_maven).
setup_maven || exit 1
# Own local repo for this job (not shared with the light job or other projects: concurrent
# Maven processes writing one local repo can corrupt it).
M2_REPO=/scratch/mjk76/ea442/.m2-fpverify-hudi
mkdir -p "$M2_REPO"
export MAVEN_OPTS="${MAVEN_OPTS:-} -Dmaven.repo.local=$M2_REPO"
# Type-check only the hudi classes that have flagged rows (see lib.sh only_defs_regex).
export ONLY_DEFS="$(only_defs_regex hudi)"
[ -n "$ONLY_DEFS" ] || { echo "FATAL: no flagged hudi classes found in results.jsonl" >&2; exit 1; }
echo "Checking only: $ONLY_DEFS"
echo "Using: $(java -version 2>&1 | head -1)"

WORK=/scratch/mjk76/ea442/fullproject-verify-work/hudi
OUT=/project/mjk76/ea442/snippet-selection-pipeline-output/fullproject-verification/hudi
mkdir -p "$OUT"
HUDI_URL=https://github.com/apache/hudi
HUDI_COMMIT=cb32e5e1bac58cbccba8c92c91e7bed4780e9858

step() { echo; echo "[$(date '+%Y-%m-%d %H:%M:%S')] === $* ==="; }

FAIL=0
FAILED_STEPS=()
run() {  # run <label> <run_hudi_checker.sh args...>; always starts from a clean tree
  local label="$1"; shift
  step "$label"
  if ! prepare_clone "$HUDI_URL" "$HUDI_COMMIT" "$WORK"; then
    FAIL=1; FAILED_STEPS+=("$label (clone not clean)"); return 1
  fi
  bash fullproject-verification/hudi/run_hudi_checker.sh "$WORK" "$@"
  local rc=$?
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] --- $label exit=$rc"
  if [ $rc -ne 0 ]; then FAIL=1; FAILED_STEPS+=("$label (exit $rc)"); fi
  return $rc
}

# 1. everything except hudi-utilities
export SKIP_UTILITIES=1 SKIP_METASERVER=1
for c in formatter regex index nullness; do
  run "hudi: $c" "$c" "$OUT"
done

# 2. hudi-utilities (optional; see header)
if run "hudi: prep for hudi-utilities (mvn install, no checker)" prep "$OUT"; then
  run "hudi: nullness on hudi-utilities" nullness-utilities "$OUT"
else
  echo "Skipping nullness on hudi-utilities: prep failed (see $OUT/prep_install.log)."
  echo "Most likely cause: packages.confluent.io unreachable from this node."
fi

step "Done. Logs under $OUT"
if [ ${#FAILED_STEPS[@]} -gt 0 ]; then
  echo "Steps with non-zero exit:"
  printf '  %s\n' "${FAILED_STEPS[@]}"
fi
exit $FAIL
