#!/bin/bash
# Run one Checker Framework 4.2.1 checker over the full mybatis-3 project.
#
# Usage: run_checker.sh <interning|nullness> <path-to-mybatis-3-clone> [log-file]
#
# The clone must be at commit ed5512752c2a744202574345631b59a6b0d0ba1e, with an unmodified
# pom.xml. This script applies pom_<checker>.patch (kept next to this script), runs the build,
# writes all compiler output to the log, and then restores pom.xml.
#
# Requirements: JDK 17 or 21 (the parent POM's enforcer accepts 17, 21, 23, 24 and 25),
# Maven >= 3.9.9, and network access to Maven Central.
#
# Note: mvn exits 1 with "COMPILATION ERROR" whenever the checker reports anything, because
# Checker Framework reports its diagnostics as javac errors by default. That is expected; the
# diagnostics are in the log. Maven prints each error twice, so run `sort -u` before counting.
set -u

CHECKER=${1:?usage: run_checker.sh <interning|nullness> <repo-dir> [log-file]}
REPO=${2:?usage: run_checker.sh <interning|nullness> <repo-dir> [log-file]}
HERE=$(cd "$(dirname "$0")" && pwd)
LOG=${3:-$HERE/mybatis-3_${CHECKER}_build.log}
PATCH=$HERE/pom_${CHECKER}.patch
EXPECTED_COMMIT=ed5512752c2a744202574345631b59a6b0d0ba1e

[ -f "$PATCH" ] || { echo "no patch for checker '$CHECKER' ($PATCH)"; exit 2; }
cd "$REPO" || exit 2

HEAD=$(git rev-parse HEAD)
[ "$HEAD" = "$EXPECTED_COMMIT" ] || { echo "warning: HEAD is $HEAD, expected $EXPECTED_COMMIT" >&2; }

git checkout -- pom.xml
git apply "$PATCH" || { echo "patch failed to apply"; exit 2; }

# Use mybatis-3's own bundled wrapper, same convention as the rest of this pipeline
# (classpath.py/config.py) - never depend on a system-wide `mvn` module on HPC.
chmod +x ./mvnw
# Keep Maven's local repo on scratch, not $HOME (same reason GRADLE_USER_HOME is
# redirected to scratch everywhere else in this project - avoids the home quota).
export MAVEN_OPTS="${MAVEN_OPTS:-} -Dmaven.repo.local=/scratch/mjk76/ea442/.m2"

# Why the -D...skip flags are needed:
# mybatis-3's parent POM (org.mybatis:mybatis-parent:48) binds four plugins to phases that run
# BEFORE compile, and each one REWRITES source files in place:
#   whitespace:trim   - strips trailing whitespace
#   formatter:format  - reformats Java sources with format.xml
#   impsort:sort      - reorders imports
#   license:format    - rewrites license headers (e.g. "Copyright 2009-2023" becomes the current year)
# Without these flags the checker would analyze modified source rather than the pinned commit,
# which can shift line numbers and taints the "same program" comparison. With them, the clone
# stays clean (`git status` shows only pom.xml, which this script restores at the end).
./mvnw -B -fae clean compile \
  -Dlicense.skip=true \
  -Dformatter.skip=true \
  -Dimpsort.skip=true \
  -Dwhitespace.skip=true \
  2>&1 | tee "$LOG"
rc=${PIPESTATUS[0]}
echo "mvn exit=$rc (1 is expected if the checker reported anything); log: $LOG"

git checkout -- pom.xml
dirty=$(git status --short)
[ -z "$dirty" ] || { echo "WARNING: source tree modified by build:"; echo "$dirty"; }

echo "unique diagnostics: $(grep -E '\.java:\[' "$LOG" | sort -u | wc -l)"
