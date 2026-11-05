#!/bin/bash -l
#SBATCH --job-name=fpverify-light
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

# Full-project checker verification for apollo, mybatis-3, netty and dubbo.
# Submit from the repo root:  sbatch fullproject-verification/submit_verify_light.sh
#
# Each repo is checked out at its pinned commit under $WORK (reused if already there, and
# always reset to a clean tree), then each repo's own run script applies its pom patch,
# runs the real Maven build with one checker, and reverts the patch.
# Per-checker logs land under $OUT/<repo>/<checker>.log.

set -uo pipefail
cd "$SLURM_SUBMIT_DIR"
source fullproject-verification/lib.sh

module purge
module load easybuild
module load Java/17.0.15
module load GCCcore/13.3.0
echo "Using: $(java -version 2>&1 | head -1)"
# One Maven 3.9.9 for all four repos (see lib.sh setup_maven), not each repo's ./mvnw.
setup_maven || exit 1

WORK=/scratch/mjk76/ea442/fullproject-verify-work
OUT=/project/mjk76/ea442/snippet-selection-pipeline-output/fullproject-verification
# Maven local repo used by every run script below. Its own directory, NOT shared with the
# hudi job or any other project: two Maven processes writing one local repo at the same
# time can leave corrupt/partial artifacts behind.
export M2_REPO=/scratch/mjk76/ea442/.m2-fpverify-light
mkdir -p "$WORK" "$OUT" "$M2_REPO"

step() { echo; echo "[$(date '+%Y-%m-%d %H:%M:%S')] === $* ==="; }

FAIL=0
FAILED_STEPS=()
run() {  # run <label> <command...>: run one checker step, record failure, keep going
  local label="$1"; shift
  step "$label"
  "$@"
  local rc=$?
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] --- $label exit=$rc"
  if [ $rc -ne 0 ]; then FAIL=1; FAILED_STEPS+=("$label (exit $rc)"); fi
}

step "apollo: clone"
if prepare_clone https://github.com/apolloconfig/apollo 5eb320f7fdf0c183904e9aff501392c878fec62f "$WORK/apollo"; then
  mkdir -p "$OUT/apollo"
  run "apollo: nullness" bash fullproject-verification/apollo/run_nullness.sh "$WORK/apollo" "$OUT/apollo/nullness.log"
else FAIL=1; FAILED_STEPS+=("apollo: clone"); fi

step "mybatis-3: clone"
if prepare_clone https://github.com/mybatis/mybatis-3 ed5512752c2a744202574345631b59a6b0d0ba1e "$WORK/mybatis-3"; then
  mkdir -p "$OUT/mybatis-3"
  # Note: mybatis-3's patches don't pass -Awarns, so checker findings are javac errors and
  # mvn exits 1 whenever the checker reports anything. That's expected; the log is what counts.
  for c in interning nullness; do
    run "mybatis-3: $c" bash fullproject-verification/mybatis-3/run_checker.sh "$c" "$WORK/mybatis-3" "$OUT/mybatis-3/$c.log"
  done
else FAIL=1; FAILED_STEPS+=("mybatis-3: clone"); fi

step "netty: clone"
if prepare_clone https://github.com/netty/netty f0a546dffa0d8644eb6c1f23433601cf464c0882 "$WORK/netty"; then
  mkdir -p "$OUT/netty"
  NR=fullproject-verification/netty/run_checker.sh
  run "netty: index"        bash $NR "$WORK/netty" index        common,resolver-dns,codec-http "$OUT/netty/index.log"
  run "netty: interning"    bash $NR "$WORK/netty" interning    common                         "$OUT/netty/interning.log"
  run "netty: resourceleak" bash $NR "$WORK/netty" resourceleak transport                      "$OUT/netty/resourceleak.log"
  run "netty: nullness"     bash $NR "$WORK/netty" nullness     common,handler,codec-http,codec-http2,resolver-dns,transport-native-unix-common "$OUT/netty/nullness.log"
else FAIL=1; FAILED_STEPS+=("netty: clone"); fi

step "dubbo: clone"
if prepare_clone https://github.com/apache/dubbo a5604cd2632471b46f66ed0217e84a68dc84a374 "$WORK/dubbo"; then
  mkdir -p "$OUT/dubbo"
  DR=fullproject-verification/dubbo/run_checker.sh
  # index targets are all in dubbo-common (see dubbo/README.md), so only that module is patched.
  run "dubbo: index"    bash $DR "$WORK/dubbo" index    dubbo-common "$OUT/dubbo/index.log"
  run "dubbo: nullness" bash $DR "$WORK/dubbo" nullness dubbo-common,dubbo-metadata/dubbo-metadata-processor,dubbo-plugin/dubbo-qos,dubbo-rpc/dubbo-rpc-api,dubbo-remoting/dubbo-remoting-netty,dubbo-rpc/dubbo-rpc-triple "$OUT/dubbo/nullness.log"
else FAIL=1; FAILED_STEPS+=("dubbo: clone"); fi

step "Done. Logs under $OUT"
if [ ${#FAILED_STEPS[@]} -gt 0 ]; then
  echo "Steps with non-zero exit (mybatis-3 exit 1 is expected, see above):"
  printf '  %s\n' "${FAILED_STEPS[@]}"
fi
exit $FAIL
