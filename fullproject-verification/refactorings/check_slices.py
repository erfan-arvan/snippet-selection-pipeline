#!/usr/bin/env python3
"""Check refactorings on the ALREADY SLICED snippets (no Specimin, no full-project build).

For each case in cases.tsv:
  * find its packaged slice in RUN/snippets/<snippet_id> (made by the pipeline's package stage),
  * copy it to a work directory (the original slice is never modified),
  * run the case's checker the same way the pipeline's check stage does
    (./gradlew clean compileJava -PcheckerClass=...), in three phases:
      before = slice as it is, after = slice with the refactoring, canary = refactored slice
      plus one deliberately unsafe statement at the top of the method (proves the checker
      really analyzed the refactored method),
  * compare the warnings inside the target method.
The refactoring comes from the same patches/<id>_*.patch used for the full projects: the changed
lines of each hunk are matched in the slice ignoring indentation (line numbers differ in a slice).

usage: check_slices.py [--run RUN_DIR] [--work WORK_DIR] [--out OUT_DIR] CASE_ID...
"""
import argparse, collections, json, os, re, shutil, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
FV = os.path.dirname(HERE)
LOCATOR = os.path.join(FV, "Locator.java")
sys.path.insert(0, os.path.join(os.path.dirname(FV), "orchestrator"))
from snippet_pipeline.checkers import parse_diagnostics  # noqa: E402  (same parser as the pipeline)

PROCESSOR = {"index": "org.checkerframework.checker.index.IndexChecker",
             "nullness": "org.checkerframework.checker.nullness.NullnessChecker"}
CANARY = {"index": ("int[] fpvCanary = new int[0]; int fpvCanaryValue = fpvCanary[1];", "array.access.unsafe.high.constant"),
          "nullness": ("Object fpvCanary = null; fpvCanary.hashCode();", "dereference.of.nullable")}


def read_case(cid):
    for line in open(os.path.join(HERE, "cases.tsv")):
        f = line.rstrip("\n").split("\t")
        if f and f[0] == cid:
            return dict(id=f[0], repo=f[1], checker=f[2], keys=f[3].split(","), file=f[4], cls=f[5],
                        method=f[6], nparams=int(f[7]))
    sys.exit(f"unknown case {cid}")


def hunks(patch_path):
    """Each hunk as (old_lines, new_lines), trimmed to the changed span (context lines only between
    the first and last change are kept), because a slice may not contain the surrounding code."""
    out, cur = [], None
    for l in open(patch_path).read().split("\n"):
        if l.startswith("@@"):
            cur = []; out.append(cur)
        elif cur is not None and l[:1] in (" ", "-", "+") and not l.startswith(("---", "+++")):
            cur.append(l)
    res = []
    for h in out:
        idx = [i for i, l in enumerate(h) if l[0] in "-+"]
        h = h[idx[0]:idx[-1] + 1]
        res.append(([l[1:] for l in h if l[0] in " -"], [l[1:] for l in h if l[0] in " +"]))
    return res


def apply_to_slice(path, patch_path):
    """Returns a list of problems (empty = applied)."""
    lines = open(path).read().split("\n")
    problems = []
    for old, new in hunks(patch_path):
        key = [x.strip() for x in old]
        hits = [i for i in range(len(lines) - len(key) + 1)
                if [x.strip() for x in lines[i:i + len(key)]] == key]
        only_imports = old and not [x for x in new if x.strip()] and all(
            x.strip().startswith("import ") or not x.strip() for x in old)
        if len(hits) != 1:
            if only_imports and not hits:
                continue                       # import the slice does not have: nothing to remove
            problems.append(f"{len(hits)} matches in the slice for:\n    " + "\n    ".join(old))
            continue
        i = hits[0]
        lines[i:i + len(key)] = new
    if not problems:
        open(path, "w").write("\n".join(lines))
    return problems


def method_range(path, case):
    p = subprocess.run(["java", LOCATOR, path], capture_output=True, text=True)
    rows = [l.split("\t") for l in p.stdout.splitlines()]
    ms = [r for r in rows if r[2] == case["method"] and int(r[3]) == case["nparams"]]
    exact = [r for r in ms if r[1] == case["cls"]]
    ms = exact or ms
    return (int(ms[0][5]), int(ms[0][6])) if len(ms) == 1 else None


def insert_canary(path, start, stmt):
    lines = open(path).read().split("\n")
    i = start - 1
    while "{" not in lines[i]:
        i += 1
    lines.insert(i + 1, "        " + stmt)
    open(path, "w").write("\n".join(lines))


def run_checker(snip, checker, log):
    cmd = ["./gradlew", "clean", "compileJava", f"-PcheckerClass={PROCESSOR[checker]}", "--console=plain"]
    try:
        p = subprocess.run(cmd, cwd=snip, capture_output=True, text=True, timeout=900)
        out, rc = p.stdout + "\n" + p.stderr, p.returncode
    except subprocess.TimeoutExpired as e:
        out, rc = f"TIMEOUT\n{e.stdout or ''}\n{e.stderr or ''}", -1
    open(log, "w").write(f"$ {' '.join(cmd)}\n(cwd={snip})\n\n{out}")
    return out, rc


def summarize(out, sliced_file, st, en):
    """Counts of keys inside the method, outside it, and keyless (= javac) errors in the file."""
    inside, outside, broken = collections.Counter(), collections.Counter(), []
    for d in parse_diagnostics(out):
        if not d["file"].replace("\\", "/").endswith(sliced_file):
            continue
        if d.get("key") is None:
            if d["severity"] == "error":
                broken.append(f'{d["line"]}: {d["message"]}')
            continue
        (inside if st <= int(d["line"]) <= en else outside)[d["key"]] += 1
    return inside, outside, broken


def check_case(cid, a):
    c = read_case(cid)
    sid = f'{c["repo"]}__{c["cls"].replace(".", "_")}__{c["method"]}__{c["nparams"]}'
    src = os.path.join(a.run, "snippets", sid)
    if not os.path.isfile(os.path.join(src, "snippet.json")):
        return [cid, "NO SLICE FOUND", sid] + [""] * 5
    meta = json.load(open(os.path.join(src, "snippet.json")))
    sliced_file = meta["sliced_file"].replace("\\", "/")
    patch = [os.path.join(HERE, "patches", f) for f in os.listdir(os.path.join(HERE, "patches"))
             if f.startswith(cid + "_") and f.endswith(".patch")]
    if len(patch) != 1:
        return [cid, f"EXPECTED ONE PATCH, FOUND {len(patch)}", sid] + [""] * 5
    od = os.path.join(a.out, cid)
    os.makedirs(od, exist_ok=True)
    stmt, canary_key = CANARY[c["checker"]]
    res = {}
    for phase in ("before", "after", "canary"):
        w = os.path.join(a.work, cid, phase)
        shutil.rmtree(w, ignore_errors=True)
        shutil.copytree(src, w, symlinks=True, ignore=shutil.ignore_patterns("build", ".gradle"))
        f = os.path.join(w, sliced_file)
        if phase != "before":
            probs = apply_to_slice(f, patch[0])
            if probs:
                open(os.path.join(od, "apply_problem.txt"), "w").write("\n".join(probs))
                return [cid, "REFACTORING DID NOT APPLY TO THE SLICE (see apply_problem.txt)", sid] + [""] * 5
            shutil.copy(f, os.path.join(od, f"{phase}.java"))
        rng = method_range(f, c)
        if not rng:
            return [cid, f"METHOD NOT FOUND IN SLICE ({phase})", sid] + [""] * 5
        if phase == "canary":
            insert_canary(f, rng[0], stmt)
            rng = method_range(f, c)
        if phase == "before":
            shutil.copy(f, os.path.join(od, "before.java"))
        print(f"  {cid} {phase}: method lines {rng[0]}-{rng[1]} ...", flush=True)
        out, rc = run_checker(w, c["checker"], os.path.join(od, f"{phase}.log"))
        res[phase] = summarize(out, sliced_file, *rng) + (rc,)
        print(f"    exit {rc}, in method {dict(res[phase][0])}, rest of file {sum(res[phase][1].values())},"
              f" javac errors {len(res[phase][2])}", flush=True)
    (bi, bo, bb, brc), (ai, ao, ab, arc), (ci, co, cb, crc) = res["before"], res["after"], res["canary"]
    target_b = {k: bi[k] for k in c["keys"]}
    target_a = {k: ai[k] for k in c["keys"]}
    new = {k: v for k, v in ai.items() if v > bi.get(k, 0)}
    verdict = ("SLICE DOES NOT COMPILE (before)" if bb else
               "CONTROL FAILED (warning not reproduced on the slice)" if not any(target_b.values()) else
               "REFACTORED SLICE DOES NOT COMPILE" if ab else
               ("WARNING GONE" + (" (but new warnings in method)" if new else "")) if not any(target_a.values()) else
               "WARNING STILL PRESENT")
    ran = ("YES: canary warning reported" if ci[canary_key] > ai[canary_key] else
           "NO: canary warning NOT reported - checker did not analyze the refactored method")
    ran += f" (other warnings in file: {sum(bo.values())} before, {sum(ao.values())} after)"
    return [cid, verdict, sid, json.dumps(target_b), json.dumps(target_a), json.dumps(new), f"{brc}/{arc}/{crc}", ran]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", default="/project/mjk76/ea442/snippet-selection-pipeline-output/original-warnings")
    ap.add_argument("--work", default="/scratch/mjk76/ea442/slice-refactor-work")
    ap.add_argument("--out", default="/project/mjk76/ea442/snippet-selection-pipeline-output/original-warnings/refactorings")
    ap.add_argument("cases", nargs="+")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    hdr = ["case", "verdict", "snippet_id", "before (target keys)", "after (target keys)",
           "new keys in method", "build exit before/after/canary", "checker ran?"]
    rows = []
    for cid in a.cases:
        print(f"[{subprocess.run(['date', '+%F %T'], capture_output=True, text=True).stdout.strip()}] === {cid} ===", flush=True)
        row = check_case(cid, a)
        rows.append(row)
        print("RESULT: " + "\t".join(row), flush=True)
    with open(os.path.join(a.out, "results.tsv"), "w") as f:
        f.write("\t".join(hdr) + "\n")
        for r in rows:
            f.write("\t".join(r) + "\n")
    print(f"\nResults: {os.path.join(a.out, 'results.tsv')}")


if __name__ == "__main__":
    main()
