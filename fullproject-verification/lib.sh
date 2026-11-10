#!/bin/bash
# Shared by the three submit_verify_*.sh jobs. Source it, don't run it.
#
# setup_maven
#   Puts Maven 3.9.9 on PATH (MAVEN_HOME, default /scratch/mjk76/ea442/apache-maven-3.9.9,
#   downloaded there once if missing) and exports MVN=mvn, which every Maven run script uses
#   instead of the repo's own ./mvnw. One fixed Maven for all repos: it is the version the
#   patches were validated with (apollo's own wrapper would pull Maven 3.5.4), and nothing
#   has to be downloaded per repo at job time.
#
# prepare_clone <url> <commit> <dest>
#   Leaves <dest> as a clean checkout of <commit>, whether or not <dest> already exists:
#   - fresh shallow fetch of exactly <commit> if <dest> is missing or at another commit
#   - core.autocrlf=false / core.filemode=false set on EVERY call, including reused clones,
#     so filesystems that don't keep exec bits (or CRLF conversion) can't make the tree
#     look modified to the run scripts' "refusing to run" guards
#   - any leftover tracked-file changes (e.g. a patch not reverted because an earlier job
#     was killed mid-build) are printed and discarded with `git reset --hard <commit>`
#   Returns non-zero, with the offending files printed, if the tree is still not clean.

prepare_clone() {
  local url="$1" commit="$2" dest="$3"
  if [ -d "$dest/.git" ] && [ "$(git -C "$dest" rev-parse HEAD 2>/dev/null)" = "$commit" ]; then
    echo "  reusing $dest (already at $commit)"
  else
    echo "  fresh clone of $url @ $commit -> $dest"
    rm -rf "$dest"
    mkdir -p "$dest"
    git init -q "$dest"
    git -C "$dest" remote add origin "$url"
  fi
  git -C "$dest" config core.autocrlf false
  git -C "$dest" config core.filemode false
  if [ "$(git -C "$dest" rev-parse HEAD 2>/dev/null)" != "$commit" ]; then
    git -C "$dest" fetch -q --depth 1 origin "$commit" || { echo "  ERROR: fetch of $commit failed" >&2; return 1; }
    git -C "$dest" checkout -q "$commit" || { echo "  ERROR: checkout of $commit failed" >&2; return 1; }
  fi
  local dirty
  dirty="$(git -C "$dest" status --porcelain --untracked-files=no)"
  if [ -n "$dirty" ]; then
    echo "  NOTE: $dest had tracked-file changes left over; discarding them:"
    echo "$dirty" | sed 's/^/    /'
    git -C "$dest" reset -q --hard "$commit"
    dirty="$(git -C "$dest" status --porcelain --untracked-files=no)"
    if [ -n "$dirty" ]; then
      echo "  ERROR: $dest is still not clean after reset:" >&2
      echo "$dirty" | sed 's/^/    /' >&2
      return 1
    fi
  fi
  # Restore exec bits git records (100755): some filesystems lose them on checkout, and
  # e.g. hudi-metaserver's thrift_binary.sh then fails with "Permission denied".
  git -C "$dest" ls-files -s | awk '$1=="100755"{print $4}' | while IFS= read -r f; do chmod +x "$dest/$f"; done
  echo "  $dest clean at $commit"
}

# only_defs_regex <repo> [run_dir]
#   Regex of the fully-qualified classes that have on-target flagged rows for <repo> in the
#   pipeline run (default legacy-import), for the checker's -AonlyDefs option: only those
#   classes are type-checked; the rest of the project is still compiled normally.
only_defs_regex() {
  python3 -I - "$1" "${2:-/project/mjk76/ea442/snippet-selection-pipeline-output/legacy-import}" <<'PY'
import json, os, re, sys
repo, run = sys.argv[1], sys.argv[2]
cls = set()
for line in open(os.path.join(run, "stats", "results.jsonl")):
    r = json.loads(line)
    if r.get("status") != "flagged" or not any(d.get("on_target") for d in r.get("diagnostics") or []):
        continue
    p = os.path.join(run, "snippets", r["snippet_id"], "snippet.json")
    if os.path.isfile(p):
        m = json.load(open(p))
        if m.get("repo") == repo and m.get("qualified_class_name"):
            cls.add(m["qualified_class_name"].replace("$", "."))
# [.] instead of \. so the regex survives Groovy/XML quoting unchanged
print("|".join(c.replace(".", "[.]") for c in sorted(cls)))
PY
}

setup_maven() {
  export MAVEN_HOME="${MAVEN_HOME:-/scratch/mjk76/ea442/apache-maven-3.9.9}"
  if [ ! -x "$MAVEN_HOME/bin/mvn" ]; then
    echo "No Maven at $MAVEN_HOME; downloading Apache Maven 3.9.9 there"
    if [ "$(basename "$MAVEN_HOME")" != apache-maven-3.9.9 ]; then
      echo "FATAL: MAVEN_HOME=$MAVEN_HOME has no bin/mvn (auto-download only creates .../apache-maven-3.9.9)" >&2
      return 1
    fi
    mkdir -p "$(dirname "$MAVEN_HOME")"
    curl -sSfL https://archive.apache.org/dist/maven/maven-3/3.9.9/binaries/apache-maven-3.9.9-bin.tar.gz \
      | tar xz -C "$(dirname "$MAVEN_HOME")" || { echo "FATAL: Maven download failed" >&2; return 1; }
  fi
  export PATH="$MAVEN_HOME/bin:$PATH"
  export MVN=mvn
  echo "Using: $(mvn -v 2>/dev/null | head -1)"
}
