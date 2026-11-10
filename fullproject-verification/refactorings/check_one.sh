#!/bin/bash
# Run one refactoring case: checker on the ORIGINAL method (control), then on the REFACTORED one.
# usage: check_one.sh <case id from cases.tsv>     (run from the repo root; called by submit_check_refactorings.sh)
# Writes $OUT/<id>/{before,after}.log, {before,after}.json and appends a line to $OUT/results.tsv.
set -uo pipefail
ID="$1"
FV="$PWD/fullproject-verification"   # absolute: git -C resolves relative paths inside the clone
R=$FV/refactorings
source $FV/lib.sh
IFS=$'\t' read -r _ REPO CHECKER KEYS FILE CLASS METHOD NPARAMS GTASK < <(grep -P "^$ID\t" $R/cases.tsv)
[ -n "${REPO:-}" ] || { echo "unknown case $ID" >&2; exit 2; }
WORK=/scratch/mjk76/ea442/fullproject-verify-work
OUT=/project/mjk76/ea442/snippet-selection-pipeline-output/fullproject-verification/refactorings
CO="$WORK/$REPO"
mkdir -p "$OUT/$ID"
declare -A URL=([dubbo]=https://github.com/apache/dubbo [netty]=https://github.com/netty/netty
                [hudi]=https://github.com/apache/hudi [ghidra]=https://github.com/NationalSecurityAgency/ghidra)
declare -A COMMIT=([dubbo]=a5604cd2632471b46f66ed0217e84a68dc84a374 [netty]=f0a546dffa0d8644eb6c1f23433601cf464c0882
                   [hudi]=cb32e5e1bac58cbccba8c92c91e7bed4780e9858 [ghidra]=93c19e3cc6733fab119ace63a39be2aec89208b3)
ONLY="${CLASS//./[.]}"
export ALLOW_SOURCE_CHANGES=1

method_range() {  # -> "start end" of CLASS.METHOD with NPARAMS params in the current checkout
  java "$FV/Locator.java" "$CO/$FILE" 2>/dev/null |
    awk -F'\t' -v c="$CLASS" -v m="$METHOD" -v n="$NPARAMS" '$2==c && $3==m && $4==n {print $6, $7; exit}'
}

run_checker() {  # <log>
  local log="$1"
  case "$REPO" in
    dubbo) bash $FV/dubbo/run_checker.sh "$CO" "$CHECKER" dubbo-common "$log" ;;
    netty) bash $FV/netty/run_checker.sh "$CO" "$CHECKER" common "$log" ;;
    hudi)  local d; d="$(mktemp -d)"
           ONLY_DEFS="$ONLY" SKIP_UTILITIES=1 SKIP_METASERVER=1 bash $FV/hudi/run_hudi_checker.sh "$CO" "$CHECKER" "$d"
           local rc=$?; cp "$d/build_$CHECKER.log" "$log"; rm -rf "$d"; return $rc ;;
    ghidra) ONLY_DEFS="$ONLY" GHIDRA_TASKS="$GTASK" bash $FV/ghidra/run_ghidra_checker.sh --init "$CO" "$CHECKER" "$log" ;;
  esac
}

for PHASE in before after; do
  echo "[$(date '+%F %T')] === $ID $PHASE ($REPO $CHECKER, $CLASS.$METHOD) ==="
  prepare_clone "${URL[$REPO]}" "${COMMIT[$REPO]}" "$CO" || exit 1
  if [ "$PHASE" = after ]; then
    git -C "$CO" apply --check "$R/patches/${ID}_"*.patch || { echo "patch does not apply" >&2; exit 1; }
    git -C "$CO" apply "$R/patches/${ID}_"*.patch && git -C "$CO" diff --stat
  fi
  read -r ST EN < <(method_range)
  [ -n "${ST:-}" ] || { echo "could not locate $CLASS.$METHOD/$NPARAMS in $FILE" >&2; exit 1; }
  run_checker "$OUT/$ID/$PHASE.log"; rc=$?
  echo "$rc" > "$OUT/$ID/$PHASE.exit"
  python3 -I $R/evaluate.py "$OUT/$ID/$PHASE.log" "$FILE" "$ST" "$EN" "$KEYS" > "$OUT/$ID/$PHASE.json"
  echo "  method lines $ST-$EN, build exit $rc: $(cat "$OUT/$ID/$PHASE.json")"
done
prepare_clone "${URL[$REPO]}" "${COMMIT[$REPO]}" "$CO" >/dev/null   # leave the clone clean

CASE_FILE="$FILE" python3 -I - "$OUT/$ID" "$ID" "$OUT/results.tsv" <<'PY'
import json, os, sys
d, cid, res = sys.argv[1:4]
b, a = (json.load(open(os.path.join(d, p + ".json"))) for p in ("before", "after"))
eb, ea = (open(os.path.join(d, p + ".exit")).read().strip() for p in ("before", "after"))
gone = all(v == 0 for v in a["target"].values())
present = any(v > 0 for v in b["target"].values())
new = {k: v for k, v in a["all_keys_in_method"].items() if v > b["all_keys_in_method"].get(k, 0)}
fname = os.environ["CASE_FILE"]
# With -Awarns every checker finding is a warning, so any *error* reported in the target file
# means the refactored code itself does not compile.
broke = any(fname in l and ("[ERROR]" in l or ": error:" in l)
            for l in open(os.path.join(d, "after.log"), errors="replace"))
verdict = ("CONTROL FAILED (warning not reproduced on original)" if not present else
           "REFACTORED CODE DOES NOT COMPILE" if broke else
           "WARNING GONE" + (" (but new warnings in method)" if new else "") if gone else
           "WARNING STILL PRESENT")
row = [cid, verdict, json.dumps(b["target"]), json.dumps(a["target"]), json.dumps(new), eb, ea]
new_file = not os.path.exists(res)
with open(res, "a") as f:
    if new_file:
        f.write("case\tverdict\tbefore(target keys)\tafter(target keys)\tnew keys in method\tbefore exit\tafter exit\n")
    f.write("\t".join(row) + "\n")
print("RESULT:", "\t".join(row))
PY
