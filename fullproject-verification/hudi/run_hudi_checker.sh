#!/bin/bash
# Run one Checker Framework 4.2.1 checker over the REAL hudi multi-module Maven build.
#
# usage:
#   run_hudi_checker.sh <hudi_clone_dir> prep                 # one-time, no checker: mvn install -DskipTests
#   run_hudi_checker.sh <hudi_clone_dir> <checker> [outdir]   # checker = formatter | index | nullness | regex
#   run_hudi_checker.sh <hudi_clone_dir> nullness-utilities [outdir]
#       nullness on hudi-utilities ONLY (its one target, BloomFilterData). Needs `prep` to have
#       succeeded first: builds -pl hudi-utilities WITHOUT -am, so upstream hudi modules come
#       from the local Maven repo instead of being re-checked. Needs packages.confluent.io.
#
# The clone must be at the pinned commit cb32e5e1bac58cbccba8c92c91e7bed4780e9858 and clean.
# For a checker run: applies patches/hudi_<checker>.patch, runs
#   mvn -B clean compile -pl <target modules> -am   (with the flags below)
# writes the full log to <outdir>/build_<checker>[_<part>].log, then ALWAYS reverts the poms
# (trap on EXIT), so each checker run is independent.
#
# Env knobs:
#   MVN=mvn                 maven binary (default: mvn on PATH)
#   SKIP_UTILITIES=1        nullness: drop hudi-utilities (needs packages.confluent.io artifacts)
#   SKIP_METASERVER=1       nullness: skip the hudi-metaserver-server run (needs docker or thrift 0.13.0)
#   METASERVER_LOCAL_THRIFT=1  use /usr/local/bin/thrift (-Pthrift-gen-source) instead of docker
#   EXTRA_MVN_ARGS="..."    appended to every mvn command (e.g. "-o" for offline on compute nodes)
set -u
PINNED=cb32e5e1bac58cbccba8c92c91e7bed4780e9858
HERE="$(cd "$(dirname "$0")" && pwd)"
H="$(cd "${1:?hudi clone dir}" && pwd)"
CHK="${2:?checker name or prep}"
OUT="$(mkdir -p "${3:-$PWD}" && cd "${3:-$PWD}" && pwd)"
MVN="${MVN:-mvn}"
EXTRA=(${EXTRA_MVN_ARGS:-})
# Skips: enforcer resolves test-jar deps at validate time (fails in a compile-only reactor);
# checkstyle/rat/scalastyle/jacoco are irrelevant to type-checking and only add failure modes.
COMMON=(-B -Denforcer.skip -Dcheckstyle.skip -Drat.skip -Dscalastyle.skip -Djacoco.skip)

head_commit="$(git -C "$H" rev-parse HEAD)"
if [ "$head_commit" != "$PINNED" ]; then
  echo "ERROR: $H is at $head_commit, expected $PINNED" >&2; exit 2
fi
if [ -n "$(git -C "$H" status --porcelain --untracked-files=no)" ]; then
  echo "ERROR: $H has modified tracked files; refusing to run (git -C $H checkout -- . to reset)" >&2; exit 2
fi

if [ "$CHK" = prep ]; then
  # Installs hudi test-jars etc. into ~/.m2 so later compile-only reactor runs can resolve
  # test-scoped hudi-*:tests artifacts (scala-maven-plugin in hudi-spark-* resolves test scope).
  # Only needed for hudi-utilities (nullness). Run on a node WITH network access.
  "$MVN" "${COMMON[@]}" ${EXTRA[@]+"${EXTRA[@]}"} install -DskipTests \
    -pl hudi-utilities,hudi-hadoop-mr,hudi-examples/hudi-examples-common -am \
    2>&1 | tee "$OUT/prep_install.log"
  exit "${PIPESTATUS[0]}"
fi

AM=(-am)
PATCH_NAME="$CHK"
case "$CHK" in
  nullness-utilities) MODS="hudi-utilities"; AM=(); PATCH_NAME=nullness ;;
  formatter) MODS="hudi-common" ;;
  regex)     MODS="hudi-common" ;;
  index)     MODS="hudi-io,hudi-common" ;;
  nullness)  MODS="hudi-io,hudi-common,hudi-hadoop-common,hudi-client/hudi-client-common,hudi-hadoop-mr,hudi-examples/hudi-examples-common"
             [ "${SKIP_UTILITIES:-0}" = 1 ] || MODS="$MODS,hudi-utilities" ;;
  *) echo "unknown checker: $CHK" >&2; exit 2 ;;
esac
PATCH="$HERE/patches/hudi_$PATCH_NAME.patch"
[ -f "$PATCH" ] || { echo "missing $PATCH" >&2; exit 2; }

revert() {
  git -C "$H" apply -R -p1 "$PATCH" 2>/dev/null || git -C "$H" checkout -- $(cd "$H" && git diff --name-only)
  echo "[run_hudi_checker] reverted poms; git status:"; git -C "$H" status --short --untracked-files=no
}
git -C "$H" apply --check -p1 "$PATCH" || { echo "patch does not apply cleanly" >&2; exit 3; }
git -C "$H" apply -p1 "$PATCH"
trap revert EXIT
git -C "$H" diff --stat

rc=0
cd "$H"
"$MVN" "${COMMON[@]}" ${EXTRA[@]+"${EXTRA[@]}"} -fae clean compile -pl "$MODS" ${AM[@]+"${AM[@]}"} 2>&1 | tee "$OUT/build_$CHK.log"
rc=${PIPESTATUS[0]}
echo "[run_hudi_checker] main reactor exit=$rc  log=$OUT/build_$CHK.log"

if [ "$CHK" = nullness ] && [ "${SKIP_METASERVER:-0}" != 1 ]; then
  # hudi-platform-service is only in the reactor under -Phudi-platform-service.
  # Its thrift sources are generated at generate-sources, by default via `docker run omnisci/thrift:0.13.0`.
  PROF=-Phudi-platform-service
  [ "${METASERVER_LOCAL_THRIFT:-0}" = 1 ] && PROF="$PROF,thrift-gen-source"
  rc2=0
  "$MVN" "${COMMON[@]}" ${EXTRA[@]+"${EXTRA[@]}"} -fae $PROF clean compile \
    -pl hudi-platform-service/hudi-metaserver/hudi-metaserver-server -am \
    2>&1 | tee "$OUT/build_${CHK}_metaserver.log"
  rc2=${PIPESTATUS[0]}
  echo "[run_hudi_checker] metaserver reactor exit=$rc2  log=$OUT/build_${CHK}_metaserver.log"
  [ $rc -eq 0 ] && rc=$rc2
fi

for f in "$OUT"/build_"$CHK"*.log; do
  echo "== $f"; grep "Reactor Summary" -A40 "$f" | grep -E "SUCCESS|FAIL|SKIP"
  echo "checker diagnostics: $(grep -cE '^\[WARNING\] .*\.java:\[[0-9]+,[0-9]+\] \[' "$f")"
done
exit $rc
