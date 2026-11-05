#!/bin/bash -l
#SBATCH --job-name=fpverify-missing
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

# The (repo, checker) runs that flagged rows need but the other three jobs never did:
#   mybatis-3 index, dubbo interning (dubbo-common), hudi resourceleak (hudi-kafka-connect),
#   hudi nullness on hudi-metaserver-server (thrift via apptainer, see hudi/docker-shim).
# Uses its own hudi clone + Maven repo, so it can run while fpverify-hudi is still running.
# Submit from the repo root:  sbatch fullproject-verification/submit_verify_missing.sh

set -uo pipefail
cd "$SLURM_SUBMIT_DIR"
source fullproject-verification/lib.sh

module purge
module load easybuild
module load Java/17.0.15
module load GCCcore/13.3.0
module load Apptainer >/dev/null 2>&1 || module load apptainer >/dev/null 2>&1 || true
setup_maven || exit 1

WORK=/scratch/mjk76/ea442/fullproject-verify-work
OUT=/project/mjk76/ea442/snippet-selection-pipeline-output/fullproject-verification
mkdir -p "$OUT/mybatis-3" "$OUT/dubbo" "$OUT/hudi"

step() { echo; echo "[$(date '+%Y-%m-%d %H:%M:%S')] === $* ==="; }
FAIL=0; FAILED_STEPS=()
run() { local label="$1"; shift; step "$label"; "$@"; local rc=$?
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] --- $label exit=$rc"
  [ $rc -eq 0 ] || { FAIL=1; FAILED_STEPS+=("$label (exit $rc)"); }; return $rc; }

# --- mybatis-3 index, dubbo interning (same Maven repo as the light job) ---
export M2_REPO=/scratch/mjk76/ea442/.m2-fpverify-light
if [ -z "${SKIP_DONE:-}" ]; then
prepare_clone https://github.com/mybatis/mybatis-3 ed5512752c2a744202574345631b59a6b0d0ba1e "$WORK/mybatis-3" &&
  run "mybatis-3: index" bash fullproject-verification/mybatis-3/run_checker.sh index "$WORK/mybatis-3" "$OUT/mybatis-3/index.log"
prepare_clone https://github.com/apache/dubbo a5604cd2632471b46f66ed0217e84a68dc84a374 "$WORK/dubbo" &&
  run "dubbo: interning" bash fullproject-verification/dubbo/run_checker.sh "$WORK/dubbo" interning dubbo-common "$OUT/dubbo/interning.log"
fi   # SKIP_DONE=1 sbatch ... skips these two (already done)

# --- hudi: separate clone + Maven repo from the running fpverify-hudi job ---
HW="$WORK/hudi-extra"
export MAVEN_OPTS="-Dmaven.repo.local=/scratch/mjk76/ea442/.m2-fpverify-hudi-extra"
export APPTAINER_CACHEDIR=/scratch/mjk76/ea442/.apptainer-cache SINGULARITY_CACHEDIR=/scratch/mjk76/ea442/.apptainer-cache
export PATH="$SLURM_SUBMIT_DIR/fullproject-verification/hudi/docker-shim:$PATH"
HR=fullproject-verification/hudi/run_hudi_checker.sh
hclone() { prepare_clone https://github.com/apache/hudi cb32e5e1bac58cbccba8c92c91e7bed4780e9858 "$HW"; }
# prep installs (no checker) everything upstream of hudi-kafka-connect, incl. hudi-common's
# tests jar, which hudi-metaserver-server also needs - so it runs first, for both steps.
export PREP_MODS=hudi-kafka-connect
if hclone && run "hudi: prep (install, no checker)" bash $HR "$HW" prep "$OUT/hudi"; then
  hclone && run "hudi: resourceleak on hudi-kafka-connect" bash $HR "$HW" resourceleak-kafka "$OUT/hudi"
  hclone && run "hudi: nullness on hudi-metaserver-server" bash $HR "$HW" nullness-metaserver "$OUT/hudi"
fi

step "Done. Logs under $OUT"
[ ${#FAILED_STEPS[@]} -eq 0 ] || { echo "Steps with non-zero exit:"; printf '  %s\n' "${FAILED_STEPS[@]}"; }
exit $FAIL
