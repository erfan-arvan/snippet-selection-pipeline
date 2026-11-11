#!/bin/bash
# Run one refactoring case: checker on the ORIGINAL method (control), then on the REFACTORED one.
# usage: check_one.sh <case id from cases.tsv>     (run from the repo root; called by submit_check_refactorings.sh)
# Writes $OUT/<id>/{before,after}.log, {before,after}.json and appends a line to $OUT/results.tsv.
set -uo pipefail
ID="$1"
FV="$PWD/fullproject-verification"   # absolute: git -C resolves relative paths inside the clone
R=$FV/refactorings
source $FV/lib.sh
IFS=$'\t' read -r _ REPO CHECKER KEYS FILE CLASS METHOD NPARAMS GTASK < <(awk -F'\t' -v id="$ID" '$1==id' $R/cases.tsv)
[ -n "${REPO:-}" ] || { echo "unknown case $ID" >&2; exit 2; }
WORK="${FPV_WORK:-/scratch/mjk76/ea442/fullproject-verify-work}"
OUT="${FPV_OUT:-/project/mjk76/ea442/snippet-selection-pipeline-output/fullproject-verification/refactorings}"
CO="$WORK/$REPO"
mkdir -p "$OUT/$ID"
rm -f "$OUT/$ID"/*.json "$OUT/$ID"/*.exit   # no stale results from an earlier run
case "$REPO" in
  dubbo)  URL=https://github.com/apache/dubbo;                 PIN=a5604cd2632471b46f66ed0217e84a68dc84a374 ;;
  netty)  URL=https://github.com/netty/netty;                  PIN=f0a546dffa0d8644eb6c1f23433601cf464c0882 ;;
  hudi)   URL=https://github.com/apache/hudi;                  PIN=cb32e5e1bac58cbccba8c92c91e7bed4780e9858 ;;
  ghidra) URL=https://github.com/NationalSecurityAgency/ghidra; PIN=93c19e3cc6733fab119ace63a39be2aec89208b3 ;;
esac
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

# Phases: before = original code (control); after = refactored code;
# canary = refactored code plus one deliberately unsafe statement at the top of the method. The
# canary warning proves the checker really analyzed the refactored method (not just "0 warnings").
case "$CHECKER" in
  index)    CANARY='int[] fpvCanary = new int[0]; int fpvCanaryValue = fpvCanary[1];'; CANARY_KEY=array.access.unsafe.high.constant ;;
  nullness) CANARY='Object fpvCanary = null; fpvCanary.hashCode();';                   CANARY_KEY=dereference.of.nullable ;;
  *)        CANARY=''; CANARY_KEY='' ;;
esac
for PHASE in before after canary; do
  [ "$PHASE" = canary ] && [ -z "$CANARY" ] && continue
  echo "[$(date '+%F %T')] === $ID $PHASE ($REPO $CHECKER, $CLASS.$METHOD) ==="
  prepare_clone "$URL" "$PIN" "$CO" || exit 1
  if [ "$PHASE" != before ]; then
    git -C "$CO" apply --check "$R/patches/${ID}_"*.patch || { echo "patch does not apply" >&2; exit 1; }
    git -C "$CO" apply "$R/patches/${ID}_"*.patch && git -C "$CO" diff --stat
  fi
  if [ "$PHASE" = canary ]; then
    read -r ST EN < <(method_range)
    python3 -I - "$CO/$FILE" "$ST" "$CANARY" <<'PY' || { echo "could not insert canary" >&2; exit 1; }
import sys
p, st, canary = sys.argv[1], int(sys.argv[2]), sys.argv[3]
lines = open(p).read().split("\n")
i = st - 1
while "{" not in lines[i]:       # skip annotations / multi-line signature up to the opening brace
    i += 1
lines.insert(i + 1, "        " + canary)
open(p, "w").write("\n".join(lines))
PY
  fi
  read -r ST EN < <(method_range)
  [ -n "${ST:-}" ] || { echo "could not locate $CLASS.$METHOD/$NPARAMS in $FILE" >&2; exit 1; }
  run_checker "$OUT/$ID/$PHASE.log"; rc=$?
  echo "$rc" > "$OUT/$ID/$PHASE.exit"
  K="$KEYS"; [ "$PHASE" = canary ] && K="$KEYS,$CANARY_KEY"
  python3 -I $R/evaluate.py "$OUT/$ID/$PHASE.log" "$FILE" "$ST" "$EN" "$K" > "$OUT/$ID/$PHASE.json"
  python3 -I $R/evaluate.py "$OUT/$ID/$PHASE.log" "$FILE" 1 9999999 "$KEYS" > "$OUT/$ID/$PHASE.file.json"
  echo "  method lines $ST-$EN, build exit $rc: $(cat "$OUT/$ID/$PHASE.json")"
done
prepare_clone "$URL" "$PIN" "$CO" >/dev/null   # leave the clone clean

CASE_FILE="$FILE" CANARY_KEY="$CANARY_KEY" python3 -I - "$OUT/$ID" "$ID" "$OUT/results.tsv" <<'PY'
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
# Evidence that the checker really analyzed the refactored file: its warnings OUTSIDE the method.
fb, fa = (json.load(open(os.path.join(d, p + ".file.json"))) for p in ("before", "after"))
ob = sum(fb["all_keys_in_method"].values()) - sum(b["all_keys_in_method"].values())
oa = sum(fa["all_keys_in_method"].values()) - sum(a["all_keys_in_method"].values())
cp = os.path.join(d, "canary.json")
if os.path.exists(cp):
    c = json.load(open(cp))
    extra = sum(c["all_keys_in_method"].values()) - sum(a["all_keys_in_method"].values())
    ran = ("YES: canary warning reported in the refactored method" if extra > 0
           else "NO: canary warning NOT reported - checker did not analyze the refactored method")
else:
    ran = "no canary for this checker"
ran += " (other warnings in file: %d before, %d after)" % (ob, oa)
row = [cid, verdict, json.dumps(b["target"]), json.dumps(a["target"]), json.dumps(new), eb, ea, ran]
new_file = not os.path.exists(res)
with open(res, "a") as f:
    if new_file:
        f.write("case\tverdict\tbefore(target keys)\tafter(target keys)\tnew keys in method\tbefore exit\tafter exit\tchecker ran?\n")
    f.write("\t".join(row) + "\n")
print("RESULT:", "\t".join(row))
PY
