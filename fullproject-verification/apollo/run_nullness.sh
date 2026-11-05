#!/usr/bin/env bash
# Apply the Checker Framework (NullnessChecker 4.2.1) patch to a fresh apollo clone
# at commit 5eb320f7fdf0c183904e9aff501392c878fec62f and run the real reactor build.
#
# Usage: run_nullness.sh <path-to-apollo-clone> [log-file]
#
# NOTE: -Awarns is a javac/Checker Framework option, NOT a Maven option. It is
# set inside the patch's <compilerArgs>; do not pass it on the mvn command line
# (Maven would reject it as an unknown option). Without -Awarns, checker errors
# in upstream modules (apollo-common, apollo-audit-*) fail the reactor before
# apollo-portal is ever compiled.
set -euo pipefail

REPO=${1:?usage: $0 <apollo-clone> [log-file]}
HERE=$(cd "$(dirname "$0")" && pwd)
LOG=${2:-$HERE/apollo_nullness_build.log}
COMMIT=5eb320f7fdf0c183904e9aff501392c878fec62f

cd "$REPO"
head=$(git rev-parse HEAD)
if [ "$head" != "$COMMIT" ]; then
  echo "error: $REPO is at $head, expected $COMMIT" >&2; exit 1
fi
if ! git diff --quiet -- pom.xml; then
  echo "error: pom.xml already modified; run 'git checkout pom.xml' first" >&2; exit 1
fi

java -version 2>&1 | head -1   # needs JDK 17+ (tested on 21)
git apply "$HERE/apollo-nullness-pom.patch"

# Use apollo's own bundled wrapper, same convention as the rest of this pipeline
# (classpath.py/config.py) - never depend on a system-wide `mvn` module on HPC.
chmod +x ./mvnw
# Keep Maven's local repo on scratch, not $HOME (same reason GRADLE_USER_HOME is
# redirected to scratch everywhere else in this project - avoids the home quota).
export MAVEN_OPTS="${MAVEN_OPTS:-} -Dmaven.repo.local=/scratch/mjk76/ea442/.m2"

set +e
./mvnw -B -fae -pl apollo-portal -am clean compile -DskipTests 2>&1 | tee "$LOG"
rc=${PIPESTATUS[0]}
set -e

git checkout -q pom.xml   # leave the clone clean
echo "mvn exit code: $rc; log: $LOG"
echo "checker warnings: $(grep -c 'WARNING.*\.java:\[' "$LOG" || true)"
exit $rc
