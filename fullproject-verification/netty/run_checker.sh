#!/bin/bash
# Run one Checker Framework 4.2.1 checker on one or more netty submodules via netty's real Maven reactor.
#
# usage: run_checker.sh <netty_clone_dir> <checker> <submodule>[,<submodule>...] [log_file]
#   checker   : index | interning | nullness | resourceleak
#   submodule : e.g. common, transport, handler, codec-http, codec-http2, resolver-dns,
#               transport-native-unix-common
#   log_file  : default <clone>/cf_<checker>.log
# env NETTY_GOAL: Maven goal, default "test-compile" (see README: plain "compile" fails
#               dependency resolution for any -am set that contains netty-codec).
#
# The clone must be at f0a546dffa0d8644eb6c1f23433601cf464c0882 with clean pom.xml files.
# Uses the pre-made patch in patches/<checker>__<submodule>.patch if present, else falls back
# to patch_pom.py (same template). Poms are reverted after.
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
CLONE="$(cd "$1" && pwd)"; CHECKER="$2"; MODS="$3"; LOG="${4:-$CLONE/cf_$2.log}"; GOAL="${NETTY_GOAL:-test-compile}"
case "$CHECKER" in
  index)        PROC=org.checkerframework.checker.index.IndexChecker ;;
  interning)    PROC=org.checkerframework.checker.interning.InterningChecker ;;
  nullness)     PROC=org.checkerframework.checker.nullness.NullnessChecker ;;
  resourceleak) PROC=org.checkerframework.checker.resourceleak.ResourceLeakChecker ;;
  *) echo "unknown checker $CHECKER" >&2; exit 2 ;;
esac
cd "$CLONE"
[ "$(git rev-parse HEAD)" = f0a546dffa0d8644eb6c1f23433601cf464c0882 ] || { echo "clone not at pinned commit" >&2; exit 2; }
git diff --quiet -- '*pom.xml' || { echo "pom.xml files not clean; run: git checkout -- \$(git ls-files '*pom.xml')" >&2; exit 2; }
revert() { git checkout -- $(git ls-files '*pom.xml'); }
trap revert EXIT
for m in ${MODS//,/ }; do
  p="$HERE/patches/${CHECKER}__${m}.patch"
  if [ -f "$p" ]; then git apply "$p"; else python3 -I "$HERE/patch_pom.py" "$CLONE/$m/pom.xml" "$PROC"; fi
done
git diff --stat
# Maven to use: $MVN if set (the submit jobs set it to one Maven 3.9.9 install, the
# version these patches were validated with), else this repo's own ./mvnw.
MVN="${MVN:-./mvnw}"
[ "$MVN" = ./mvnw ] && chmod +x "./mvnw"
# Keep Maven's local repo on scratch, not $HOME (same reason GRADLE_USER_HOME is
# redirected to scratch everywhere else in this project - avoids the home quota).
export MAVEN_OPTS="${MAVEN_OPTS:-} -Dmaven.repo.local=${M2_REPO:-/scratch/mjk76/ea442/.m2}"
# clean: so patched modules are really recompiled (maven-compiler-plugin 3.8.0 does not detect pom changes)
"$MVN" -B -fae -pl "$MODS" -am clean "$GOAL" -DskipTests -Dcheckstyle.skip=true -Danimal.sniffer.skip=true \
  2>&1 | tee "$LOG"
rc=${PIPESTATUS[0]}
echo "mvn rc=$rc  log: $LOG"
grep -E "BUILD (SUCCESS|FAILURE)" "$LOG"
# Checker warnings look like: [WARNING] /path/File.java:[line,col] [message.key] text
exit $rc
