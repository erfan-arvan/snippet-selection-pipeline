#!/bin/bash
# Run one Checker Framework 4.2.1 checker on one or more netty submodules via netty's real Maven reactor.
#
# usage: run_checker.sh <netty_clone_dir> <checker> <submodule>[,<submodule>...] [maven_goal]
#   checker   : index | interning | nullness | resourceleak
#   submodule : e.g. common, transport, handler, codec-http, codec-http2, resolver-dns,
#               transport-native-unix-common
#   maven_goal: default "test-compile" (see README: plain "compile" fails dependency resolution
#               for any -am set that contains netty-codec). Pass "compile" to override.
#
# The clone must be at f0a546dffa0d8644eb6c1f23433601cf464c0882 with clean pom.xml files.
# Uses the pre-made patch in patches/<checker>__<submodule>.patch if present, else falls back
# to patch_pom.py (same template). Output log: <clone>/cf_<checker>.log. Poms are reverted after.
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
CLONE="$(cd "$1" && pwd)"; CHECKER="$2"; MODS="$3"; GOAL="${4:-test-compile}"
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
# clean: so patched modules are really recompiled (maven-compiler-plugin 3.8.0 does not detect pom changes)
mvn -B -pl "$MODS" -am clean "$GOAL" -DskipTests -Dcheckstyle.skip=true -Danimal.sniffer.skip=true \
  2>&1 | tee "$CLONE/cf_${CHECKER}.log"
rc=${PIPESTATUS[0]}
echo "mvn rc=$rc  log: $CLONE/cf_${CHECKER}.log"
grep -E "BUILD (SUCCESS|FAILURE)" "$CLONE/cf_${CHECKER}.log"
# Checker warnings look like: [WARNING] /path/File.java:[line,col] [message.key] text
exit $rc
