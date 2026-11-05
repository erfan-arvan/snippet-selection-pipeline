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
# There is no Maven module on Wulver at all; use the Maven 3.9.9 already manually
# installed under this account for other project work (promptstudy's
# run_daikonpp_hudi_java_client.sh), same layout: scratch-local install + scratch-local
# .m2 repo, so this doesn't touch the home quota either.
export MAVEN_HOME="/scratch/mjk76/ea442/apache-maven-3.9.9"
export PATH="$MAVEN_HOME/bin:$PATH"
export MAVEN_OPTS="-Dmaven.repo.local=/scratch/mjk76/ea442/.m2"
if ! command -v mvn >/dev/null 2>&1; then
  echo "FATAL: no 'mvn' at $MAVEN_HOME/bin on this node. Set MAVEN_HOME=<path> yourself if it moved." >&2
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
  # Disable any checkout-time normalization (CRLF conversion, file-mode tracking) that
  # could make a byte-for-byte fresh checkout look "dirty" to git before anything has
  # even touched it - which would otherwise trip run_hudi_checker.sh's own
  # modified-tree safety guard on every single invocation (confirmed: this happened).
  git -C "$WORK" config core.autocrlf false
  git -C "$WORK" config core.filemode false
  git -C "$WORK" remote add origin https://github.com/apache/hudi
  git -C "$WORK" fetch --depth 1 origin cb32e5e1bac58cbccba8c92c91e7bed4780e9858
  git -C "$WORK" checkout -q cb32e5e1bac58cbccba8c92c91e7bed4780e9858
fi
dirty="$(git -C "$WORK" status --porcelain --untracked-files=no)"
if [ -n "$dirty" ]; then
  echo "WARNING: clone reported dirty before any patch was applied; resetting: $dirty"
  git -C "$WORK" checkout -- .
fi

FAIL=0
step "prep (one-time: mvn install -DskipTests)"
bash fullproject-verification/hudi/run_hudi_checker.sh "$WORK" prep || FAIL=1

for c in formatter index nullness regex; do
  step "hudi checker: $c"
  bash fullproject-verification/hudi/run_hudi_checker.sh "$WORK" "$c" "$OUT" || FAIL=1
done

step "Done. Logs under $OUT"
# Propagate any step's failure into this job's own exit code/sacct state - otherwise
# the job shows COMPLETED even if every single checker step failed (confirmed: this happened).
exit $FAIL
