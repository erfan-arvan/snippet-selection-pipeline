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
#SBATCH --time=12:00:00

# Full-project checker verification for the 4 repos whose patches are already validated
# (apollo, mybatis-3) or mostly validated (netty, dubbo) with a real passing build in the
# sandbox that produced them. Runs each repo's own run_checker.sh (committed alongside this
# script) against a FRESH clone at the pinned commit - never against /scratch/.../repos-pinned,
# to avoid racing with the main pipeline if it's running concurrently.
#
# Each run_checker.sh already: applies its own pom.xml patch, runs the real Maven reactor
# build with that one checker enabled, and reverts the patch when it exits (even on failure) -
# see each repo's own README.md under fullproject-verification/<repo>/ for exact gotchas.

set -uo pipefail
cd "$SLURM_SUBMIT_DIR"

module purge
module load easybuild
module load Java/17.0.15
module load GCCcore/13.3.0

# No system-wide Maven module needed: apollo, mybatis-3, netty and dubbo all ship their
# own ./mvnw wrapper, which each run_checker.sh now uses directly (same convention as
# the rest of this pipeline - see orchestrator/snippet_pipeline/classpath.py). The
# wrapper self-bootstraps its own pinned Maven distribution on first run.
echo "Using: $(java -version 2>&1 | head -1)"

WORK=/scratch/mjk76/ea442/fullproject-verify-work
OUT=/project/mjk76/ea442/snippet-selection-pipeline-output/fullproject-verification
mkdir -p "$WORK" "$OUT"

# Timestamped step banner, so `tail -f fpverify-light.<jobid>.out` shows overall progress
# (which repo/checker is running, and when each one started) on top of the live build output
# each run_checker.sh now also streams here (via `tee`, not just redirected to its own log).
step() { echo; echo "[$(date '+%Y-%m-%d %H:%M:%S')] === $* ==="; }

clone_at() {  # clone_at <url> <commit> <dest>
  local url="$1" commit="$2" dest="$3"
  if [ -d "$dest/.git" ] && [ "$(git -C "$dest" rev-parse HEAD 2>/dev/null)" = "$commit" ]; then
    echo "  $dest already at $commit"
    return
  fi
  rm -rf "$dest"
  mkdir -p "$dest"
  git init -q "$dest"
  git -C "$dest" remote add origin "$url"
  git -C "$dest" fetch --depth 1 origin "$commit"
  git -C "$dest" checkout -q "$commit"
}

step "apollo (nullness)"
clone_at https://github.com/apolloconfig/apollo 5eb320f7fdf0c183904e9aff501392c878fec62f "$WORK/apollo"
mkdir -p "$OUT/apollo"
bash fullproject-verification/apollo/run_nullness.sh "$WORK/apollo" "$OUT/apollo/nullness.log"

step "mybatis-3 (interning, nullness)"
clone_at https://github.com/mybatis/mybatis-3 ed5512752c2a744202574345631b59a6b0d0ba1e "$WORK/mybatis-3"
mkdir -p "$OUT/mybatis-3"
for c in interning nullness; do
  step "mybatis-3: $c"
  bash fullproject-verification/mybatis-3/run_checker.sh "$c" "$WORK/mybatis-3" "$OUT/mybatis-3/$c.log"
done

step "netty (index, interning, resourceleak, nullness)"
clone_at https://github.com/netty/netty f0a546dffa0d8644eb6c1f23433601cf464c0882 "$WORK/netty"
mkdir -p "$OUT/netty"
step "netty: index"
bash fullproject-verification/netty/run_checker.sh "$WORK/netty" index common,resolver-dns,codec-http "$OUT/netty/index.log"
step "netty: interning"
bash fullproject-verification/netty/run_checker.sh "$WORK/netty" interning common "$OUT/netty/interning.log"
step "netty: resourceleak"
bash fullproject-verification/netty/run_checker.sh "$WORK/netty" resourceleak transport "$OUT/netty/resourceleak.log"
step "netty: nullness"
bash fullproject-verification/netty/run_checker.sh "$WORK/netty" nullness common,handler,codec-http,codec-http2,resolver-dns,transport-native-unix-common "$OUT/netty/nullness.log"

step "dubbo (index, nullness)"
clone_at https://github.com/apache/dubbo a5604cd2632471b46f66ed0217e84a68dc84a374 "$WORK/dubbo"
mkdir -p "$OUT/dubbo"
step "dubbo: index"
bash fullproject-verification/dubbo/run_checker.sh "$WORK/dubbo" index dubbo-common,dubbo-metadata/dubbo-metadata-processor,dubbo-plugin/dubbo-qos,dubbo-rpc/dubbo-rpc-api,dubbo-remoting/dubbo-remoting-netty,dubbo-rpc/dubbo-rpc-triple "$OUT/dubbo/index.log"
step "dubbo: nullness"
bash fullproject-verification/dubbo/run_checker.sh "$WORK/dubbo" nullness dubbo-common,dubbo-metadata/dubbo-metadata-processor,dubbo-plugin/dubbo-qos,dubbo-rpc/dubbo-rpc-api,dubbo-remoting/dubbo-remoting-netty,dubbo-rpc/dubbo-rpc-triple "$OUT/dubbo/nullness.log"

step "Done. Logs under $OUT"
