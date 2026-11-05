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

# Unlike apollo/mybatis-3/netty/dubbo/ghidra, hudi does NOT ship its own ./mvnw wrapper
# (confirmed: no mvnw at the pinned commit) - it genuinely needs a real Maven on PATH.
# Try a module first (name varies by site; override with MAVEN_MODULE=<name> if these
# miss), and if none resolve, bootstrap Maven directly from Apache's archive into
# scratch instead of guessing further.
for m in "${MAVEN_MODULE:-}" Maven/3.9.6 Maven/3.9.9 maven; do
  [ -z "$m" ] && continue
  module load "$m" 2>/dev/null && { echo "Loaded Maven module: $m"; break; }
done
if ! command -v mvn >/dev/null 2>&1; then
  echo "No Maven module resolved; bootstrapping Apache Maven 3.9.9 directly into scratch."
  MVN_DIST=/scratch/mjk76/ea442/.maven-dist/apache-maven-3.9.9
  if [ ! -x "$MVN_DIST/bin/mvn" ]; then
    mkdir -p "$(dirname "$MVN_DIST")"
    curl -sSL -o "$(dirname "$MVN_DIST")/maven.tar.gz" \
      https://dlcdn.apache.org/maven/maven-3/3.9.9/binaries/apache-maven-3.9.9-bin.tar.gz
    tar -xzf "$(dirname "$MVN_DIST")/maven.tar.gz" -C "$(dirname "$MVN_DIST")"
    rm -f "$(dirname "$MVN_DIST")/maven.tar.gz"
  fi
  export PATH="$MVN_DIST/bin:$PATH"
fi
if ! command -v mvn >/dev/null 2>&1; then
  echo "FATAL: still no 'mvn' on PATH after module-load and direct-download attempts." >&2
  echo "  Run 'module avail Maven' yourself, then: MAVEN_MODULE=<name> sbatch fullproject-verification/submit_verify_hudi.sh" >&2
  exit 1
fi
echo "Using: $(mvn -v | head -1)"

export SKIP_UTILITIES=1
export SKIP_METASERVER=1

WORK=/scratch/mjk76/ea442/fullproject-verify-work/hudi
OUT=/project/mjk76/ea442/snippet-selection-pipeline-output/fullproject-verification/hudi
mkdir -p "$OUT"

# Timestamped step banner - tail -f fpverify-hudi.<jobid>.out to watch progress; run_hudi_checker.sh
# now streams its build output here live too (via tee), not just into its own log file.
step() { echo; echo "[$(date '+%Y-%m-%d %H:%M:%S')] === $* ==="; }

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

step "prep (one-time: mvn install -DskipTests)"
bash fullproject-verification/hudi/run_hudi_checker.sh "$WORK" prep

for c in formatter index nullness regex; do
  step "hudi checker: $c"
  bash fullproject-verification/hudi/run_hudi_checker.sh "$WORK" "$c" "$OUT"
done

step "Done. Logs under $OUT"
