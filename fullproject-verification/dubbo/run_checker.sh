#!/usr/bin/env bash
# Run one Checker Framework checker on one (or more) dubbo submodules via dubbo's real Maven reactor.
#
# Usage:
#   run_checker.sh <dubbo_clone_dir> <index|nullness> <submodule>[,<submodule>...] [<log_file>]
# Examples:
#   run_checker.sh ./dubbo index dubbo-common
#   run_checker.sh ./dubbo nullness dubbo-rpc/dubbo-rpc-triple logs/triple_nullness.log
#
# The clone must be apache/dubbo at a5604cd2632471b46f66ed0217e84a68dc84a374, e.g.:
#   git init dubbo && cd dubbo && git remote add origin https://github.com/apache/dubbo \
#     && git fetch --depth 1 origin a5604cd2632471b46f66ed0217e84a68dc84a374 \
#     && git checkout a5604cd2632471b46f66ed0217e84a68dc84a374
#
# Requirements: JDK 17+ (validated on OpenJDK 21.0.12), Maven 3.9.x (validated on 3.9.11), python3.
# The pom edits are reverted on exit (including on failure/Ctrl-C), so each run is independent.
set -euo pipefail

if [[ $# -lt 3 ]]; then
  sed -n '2,16p' "$0"; exit 2
fi
REPO=$(cd "$1" && pwd)
CHECKER=$2
MODULES=$3
LOG=${4:-"$PWD/dubbo_${CHECKER}_$(echo "$MODULES" | tr '/,' '__').log"}
HERE=$(cd "$(dirname "$0")" && pwd)
PINNED=a5604cd2632471b46f66ed0217e84a68dc84a374

head=$(git -C "$REPO" rev-parse HEAD)
if [[ "$head" != "$PINNED" ]]; then
  echo "WARNING: $REPO is at $head, not the pinned $PINNED" >&2
fi
if ! git -C "$REPO" diff --quiet -- '*pom.xml'; then
  echo "ERROR: $REPO has modified pom.xml files; clean them first (git checkout -- <pom>)" >&2
  exit 1
fi

IFS=',' read -r -a MODS <<< "$MODULES"
POMS=()
for m in "${MODS[@]}"; do POMS+=("$m/pom.xml"); done

revert() { git -C "$REPO" checkout -- "${POMS[@]}" && echo "reverted: ${POMS[*]}"; }
trap revert EXIT

# Use dubbo's own bundled wrapper, same convention as the rest of this pipeline
# (classpath.py/config.py) - never depend on a system-wide `mvn` module on HPC.
chmod +x "$REPO/mvnw"

# --- Gotcha 1: dubbo-maven-plugin must be installed first --------------------------------
# dubbo-rpc-triple (and anything downstream of it, e.g. dubbo-qos, dubbo-metadata-processor)
# uses org.apache.dubbo:dubbo-maven-plugin:3.3.4-SNAPSHOT to run protoc in generate-sources.
# That plugin is built in the same reactor, but at the `compile` phase its plugin descriptor
# (META-INF/maven/plugin.xml) has not been generated yet, so the build fails with
# "No plugin descriptor found". Installing it once into ~/.m2 (no checker) fixes that.
if [[ ! -d "$HOME/.m2/repository/org/apache/dubbo/dubbo-maven-plugin/3.3.4-SNAPSHOT" ]]; then
  echo "Installing dubbo-maven-plugin (one-time, no checker) ..."
  (cd "$REPO" && ./mvnw -B -pl dubbo-maven-plugin -am install -DskipTests \
      -Dspotless.skip=true -Dcheckstyle.skip=true -Drat.skip=true -Dmaven.javadoc.skip=true -Dgpg.skip) \
      2>&1 | tee "$LOG.plugin-install"
  [[ ${PIPESTATUS[0]} -eq 0 ]] || { echo "plugin install failed, see $LOG.plugin-install" >&2; exit 1; }
fi

python3 -I "$HERE/patch_pom.py" "$REPO" "$CHECKER" "${MODS[@]}"

# --- Gotcha 2: JAVA_TOOL_OPTIONS breaks dubbo-rpc-triple's protoc step -------------------
# If JAVA_TOOL_OPTIONS is set, every child JVM prints "Picked up JAVA_TOOL_OPTIONS: ..." to
# stderr, including dubbo's protoc-gen-tri plugin. DubboProtocCompilerMojo treats ANY protoc
# stderr as a problem and then silently does not add target/generated-sources/protobuf/java as a
# source root, so triple then fails with "package io.grpc.health.v1 does not exist".
# Move it into MAVEN_OPTS (so Maven itself keeps any proxy/truststore settings) and unset it.
if [[ -n "${JAVA_TOOL_OPTIONS:-}" ]]; then
  export MAVEN_OPTS="${MAVEN_OPTS:-} $JAVA_TOOL_OPTIONS"
  unset JAVA_TOOL_OPTIONS
fi

echo "Running: mvn -pl $MODULES -am clean compile   (log: $LOG)"
set +e
(cd "$REPO" && ./mvnw -B -fae -pl "$MODULES" -am clean compile \
    -Dspotless.skip=true -Dcheckstyle.skip=true -Drat.skip=true) 2>&1 | tee "$LOG"
rc=${PIPESTATUS[0]}
set -e
echo "mvn exit code: $rc"
grep -E "BUILD (SUCCESS|FAILURE)|Total time" "$LOG" || true
echo "checker warnings: $(grep -c '^\[WARNING\] /.*\.java:\[[0-9]*,[0-9]*\] \[' "$LOG" || true)"
exit $rc
