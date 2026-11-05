#!/usr/bin/env python3
"""For every checker warning found on a SLICED snippet's target method, decide whether the same
warning also appears when the same checker runs on the ORIGINAL full project.

usage:
  python3 compare_results.py <run_dir> [--logs <dir>] [--out <csv>]

  <run_dir>  pipeline run directory with stats/results.jsonl and snippets/<id>/snippet.json
             (the same input orchestrator/scripts/extract_flagged_paths.py reads), e.g.
             /project/mjk76/ea442/snippet-selection-pipeline-output/legacy-import
  --logs     root of the full-project logs written by the submit_verify_*.sh jobs
             (default /project/mjk76/ea442/snippet-selection-pipeline-output/fullproject-verification)
  --out      per-row result CSV (default: <logs>/comparison.csv)
  --clones   root of the full-project checkouts at the pinned commits, one dir per repo
             (default /scratch/mjk76/ea442/fullproject-verify-work). Used when snippet.json has no
             original_start_line/original_end_line (true for legacy-import: the old xlsx export
             had no line ranges): the method is located in <clones>/<repo>/<original_file> with
             Locator.java (needs `java` >= 17 on PATH), matching class + method name + number of
             parameters (as snippet ids do), and parameter types if that is still ambiguous.

What counts as "the same warning": same checker, same Checker Framework key, reported in the
same original source file, on a line inside the target method's original line range
(snippet.json original_start_line..original_end_line). Messages are NOT compared: the full build
uses real parameter names where the slice has stubs (arg0, parameter1), so text differs.

Duplicates:
  sliced side   - the same (snippet, checker) appearing in several results.jsonl records (e.g.
                  re-runs/batches) is a duplicate: only the LAST record is used. Inside one record,
                  identical (line, key, message) rows are kept: they are separate diagnostics on
                  the same line (e.g. both operands of one `==`), since the sliced log has no column.
  full side     - Maven prints every diagnostic twice and some modules compile twice; full-project
                  diagnostics are de-duplicated on (file, line, column, key, message).

Per (snippet, checker, key) group, with n = sliced occurrences, m = full-project occurrences:
  persists            m >= n
  persists_partial    0 < m < n        (fewer occurrences in the original; review by hand)
  absent              m == 0 and the checker demonstrably ran on that file's module (Maven: the
                      log has checker output from that module; Gradle: its compile task ran and
                      did not fail) -> the warning exists only in the slice (slicing artifact)
  unverified          m == 0 but that evidence is missing (module not compiled, checker not
                      enabled there, or its Gradle task FAILED)
  no_log              no full-project log for this repo + checker
Rows that are not on the target method (status slice_suspect) or have no checker key
(slice_broken: the slice did not compile) are listed as not_compared.
"""
from __future__ import annotations

import argparse
import collections
import csv
import glob
import json
import os
import re
import subprocess
import sys

DEFAULT_LOGS = "/project/mjk76/ea442/snippet-selection-pipeline-output/fullproject-verification"
DEFAULT_CLONES = "/scratch/mjk76/ea442/fullproject-verify-work"
HERE = os.path.dirname(os.path.abspath(__file__))

# [WARNING] /abs/File.java:[12,34] [key] msg   (Maven; mybatis-3 prints [ERROR] ... error: [key];
#                                                some summary lines have no [LEVEL] prefix)
MAVEN_RE = re.compile(r"^(?:\[(?:WARNING|ERROR)\]\s+)?(/\S+?\.java):\[(\d+),(\d+)\]\s+(?:(?:error|warning):\s+)?\[([\w.]+)\]\s*(.*)$")
# /abs/File.java:12: warning: [key] msg           (javac via Gradle - ghidra)
JAVAC_RE = re.compile(r"^(/\S+?\.java):(\d+):\s+(?:warning|error):\s+\[([\w.]+)\]\s*(.*)$")
GRADLE_TASK_RE = re.compile(r"^> Task :([\w.-]+):(compile\w*Java)(?:\s+(\S.*))?$")


def load_sliced(run_dir):
    """-> (on-target rows, not-compared rows, duplicate-record report)"""
    results = os.path.join(run_dir, "stats", "results.jsonl")
    if not os.path.isfile(results):
        sys.exit(f"{results} not found")
    last = {}
    seen = collections.Counter()
    with open(results) as f:
        for line in f:
            if not line.strip():
                continue
            r = json.loads(line)
            if r.get("status") not in ("flagged", "slice_suspect", "slice_broken"):
                continue
            k = (r["snippet_id"], r["checker_id"])
            seen[k] += 1
            last[k] = r
    dup_records = {k: c for k, c in seen.items() if c > 1}

    meta_cache = {}

    def meta(sid):
        if sid not in meta_cache:
            p = os.path.join(run_dir, "snippets", sid, "snippet.json")
            meta_cache[sid] = json.load(open(p)) if os.path.isfile(p) else None
        return meta_cache[sid]

    on_target, not_compared = [], []
    for (sid, cid), r in last.items():
        m = meta(sid)
        base = {"snippet_id": sid, "checker_id": cid, "status": r["status"],
                "num_params": m and m.get("num_params"), "signature": m and m.get("target_method_signature"),
                "repo": m and m.get("repo"), "original_file": m and m.get("original_file"),
                "start": m and m.get("original_start_line"), "end": m and m.get("original_end_line"),
                "qualified_class_name": m and m.get("qualified_class_name"),
                "method_name": m and m.get("method_name")}
        diags = r.get("diagnostics") or []
        if m is None:
            not_compared.append({**base, "key": None, "reason": "no snippet.json"})
            continue
        if not diags:
            not_compared.append({**base, "key": None, "reason": f"{r['status']} with no parsed diagnostics"})
            continue
        for d in diags:
            row = {**base, "key": d.get("key"), "sliced_line": d.get("line"), "sliced_message": d.get("message")}
            if not d.get("on_target"):
                not_compared.append({**row, "reason": "not on target method"})
            elif not d.get("key"):
                not_compared.append({**row, "reason": "no checker key (plain javac error: slice did not compile)"})
            else:
                on_target.append(row)
    return on_target, not_compared, dup_records


def _simple(t):
    t = re.sub(r"<.*>", "", t or "").replace("...", "[]").strip()
    t = re.sub(r"@\S+\s+", "", t)              # drop type annotations
    return t.split(".")[-1].replace(" ", "")


def normalize_paths(rows, clones_root):
    """snippet.json original_file can carry a layout prefix (legacy-import: "source/Ghidra/...").
    Drop leading components until the file exists in <clones>/<repo>/, so the path matches the
    clone and the full-project logs. Keeps the original value when nothing matches."""
    cache = {}
    for r in rows:
        f, repo = r.get("original_file"), r.get("repo")
        if not f or not repo:
            continue
        if (repo, f) not in cache:
            parts = f.replace("\\", "/").split("/")
            hit = next(("/".join(parts[i:]) for i in range(len(parts))
                        if os.path.isfile(os.path.join(clones_root, repo, *parts[i:]))), None)
            if hit is None and parts[0] == "source":
                hit = "/".join(parts[1:])
            cache[(repo, f)] = hit or f
        r["original_file"] = cache[(repo, f)]


def locate_ranges(rows, clones_root):
    """Fill r["start"]/r["end"] for rows that lack them, from the original source. Sets r["range_source"]."""
    need = collections.defaultdict(set)
    for r in rows:
        if r.get("start") is not None and r.get("end") is not None:
            r["range_source"] = "snippet.json"
        elif r.get("repo") and r.get("original_file"):
            need[r["repo"]].add(r["original_file"])
    found = collections.defaultdict(list)   # (repo, original_file) -> [(cls, name, n, types, s, e)]
    for repo, files in need.items():
        root = os.path.join(clones_root, repo)
        paths = [os.path.join(root, f) for f in sorted(files) if os.path.isfile(os.path.join(root, f))]
        if not paths:
            continue
        for i in range(0, len(paths), 200):
            p = subprocess.run(["java", os.path.join(HERE, "Locator.java")] + paths[i:i + 200],
                               capture_output=True, text=True)
            if p.returncode != 0:
                print(f"WARNING: Locator failed for {repo}: {p.stderr.strip()[:300]}", file=sys.stderr)
            for line in p.stdout.splitlines():
                f, cls, name, n, types, st, en = line.split("\t")
                found[(repo, os.path.relpath(f, root))].append((cls, name, int(n), types, int(st), int(en)))
    for r in rows:
        if r.get("range_source"):
            continue
        key = (r.get("repo"), r.get("original_file"))
        if not os.path.isfile(os.path.join(clones_root, str(key[0]), str(key[1]))):
            r["range_source"] = f"not found: no {clones_root}/{key[0]}/{key[1]}"
            continue
        q = (r.get("qualified_class_name") or "").replace("$", ".")
        cands = [c for c in found[key] if c[0] == q and c[1] == r.get("method_name")]
        if r.get("num_params") is not None:
            cands = [c for c in cands if c[2] == int(r["num_params"])]
        if len(cands) > 1 and r.get("signature") and "(" in r["signature"]:
            want = [_simple(t) for t in r["signature"].split("(", 1)[1].rstrip(")").split(",") if t.strip()]
            exact = [c for c in cands if [_simple(t) for t in c[3].split(",") if t] == want]
            if exact:
                cands = exact
        if not cands:
            r["range_source"] = f"not found: no {q}.{r.get('method_name')} with {r.get('num_params')} params in original"
            continue
        r["start"], r["end"] = min(c[4] for c in cands), max(c[5] for c in cands)
        r["range_source"] = "located in original" + ("" if len(cands) == 1 else f" (AMBIGUOUS: {len(cands)} overloads, union of their ranges)")


def log_files(logs_root, repo, checker):
    d = os.path.join(logs_root, repo)
    pats = [f"{checker}.log", f"build_{checker}.log", f"build_{checker}-*.log", f"build_{checker}_*.log"]
    out = []
    for p in pats:
        out += sorted(glob.glob(os.path.join(d, p)))
    return [f for f in out if not f.endswith((".init", ".plugin-install"))]


class FullLog:
    """All checker diagnostics (de-duplicated) + which modules compiled, from one repo/checker's logs."""

    def __init__(self, files):
        self.files = files
        self.raw = 0
        uniq = {}
        self.gradle_tasks = {}           # (project, task) -> outcome ("" = executed)
        for fn in files:
            with open(fn, errors="replace") as f:
                for line in f:
                    line = line.rstrip("\n")
                    m = MAVEN_RE.match(line)
                    if m:
                        path, ln, col, key, msg = m.group(1), int(m.group(2)), int(m.group(3)), m.group(4), m.group(5)
                    else:
                        m = JAVAC_RE.match(line)
                        if m:
                            path, ln, col, key, msg = m.group(1), int(m.group(2)), None, m.group(3), m.group(4)
                    if m:
                        self.raw += 1
                        uniq.setdefault((path, ln, col, key, msg.strip()), None)
                        continue
                    t = GRADLE_TASK_RE.match(line)
                    if t:
                        prev = self.gradle_tasks.get((t.group(1), t.group(2)))
                        outcome = (t.group(3) or "").strip()
                        # keep the worst outcome seen (FAILED beats a later/earlier success line)
                        if prev is None or outcome == "FAILED":
                            self.gradle_tasks[(t.group(1), t.group(2))] = outcome
        self.diags = list(uniq)
        self.by_file = collections.defaultdict(list)
        for d in self.diags:
            self.by_file[d[0]].append(d)

    def matches(self, original_file, key, start, end):
        out = []
        for path, ds in self.by_file.items():
            if path.endswith("/" + original_file):
                out += [d for d in ds if d[3] == key and start <= d[1] <= end]
        return sorted(set(out), key=lambda d: (d[1], d[2] or 0))

    def module_evidence(self, original_file):
        """-> (ran, note): did the checker demonstrably run over original_file's module?"""
        if original_file.startswith("src/"):
            mod, rest = "", original_file[len("src/"):]
        else:
            mod, _, rest = original_file.partition("/src/")
        srcset = rest.split("/", 1)[0] or "main"
        marker = (f"/{mod}/src/{srcset}/" if mod else f"/src/{srcset}/")
        has_diag = any(marker in p for p in self.by_file)
        if self.gradle_tasks:  # Gradle build (ghidra): use the compile task's outcome
            proj = mod.split("/")[-1]
            task = "compileJava" if srcset == "main" else f"compile{srcset[:1].upper()}{srcset[1:]}Java"
            outcome = self.gradle_tasks.get((proj, task))
            if outcome is None:
                return False, f"task :{proj}:{task} not in log"
            if outcome == "FAILED":
                # javac keeps reporting after a checker crash, so output may still be complete
                # for other files - but absence cannot be trusted.
                return False, f":{proj}:{task} FAILED" + (" (module did produce checker output)" if has_diag else "")
            if outcome:
                return False, f":{proj}:{task} {outcome}"
            return True, f":{proj}:{task} executed"
        # Maven: newer maven-compiler-plugin prints a relative "to target/classes", so the
        # compile line can't be tied to a module. Checker output from the same module is the
        # evidence that the checker was enabled there and the module was compiled.
        if has_diag:
            return True, "checker output present from this module"
        return False, "no checker output from this module (not compiled, or checker not enabled there)"


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("run_dir")
    ap.add_argument("--logs", default=DEFAULT_LOGS)
    ap.add_argument("--out")
    ap.add_argument("--clones", default=DEFAULT_CLONES)
    a = ap.parse_args()
    out_csv = a.out or os.path.join(a.logs, "comparison.csv")

    rows, not_compared, dup_records = load_sliced(a.run_dir)
    normalize_paths(rows, a.clones)
    normalize_paths(not_compared, a.clones)
    locate_ranges(rows, a.clones)

    groups = collections.OrderedDict()
    for r in rows:
        groups.setdefault((r["snippet_id"], r["checker_id"], r["key"]), []).append(r)

    logs = {}
    out = []
    for (sid, cid, key), rs in groups.items():
        r0 = rs[0]
        repo, of, s, e = r0["repo"], r0["original_file"], r0["start"], r0["end"]
        if (repo, cid) not in logs:
            fs = log_files(a.logs, repo, cid)
            logs[(repo, cid)] = FullLog(fs) if fs else None
        fl = logs[(repo, cid)]
        n = len(rs)
        if fl is None:
            verdict, m, evidence, mod_note = "no_log", 0, "", f"no log under {a.logs}/{repo}/ for {cid}"
        elif s is None or e is None:
            verdict, m, evidence, mod_note = "unverified", 0, "", f"method range unknown: {r0['range_source']}"
        else:
            hits = fl.matches(of, key, s, e)
            m = len(hits)
            ran, mod_note = fl.module_evidence(of)
            evidence = " | ".join(f"{os.path.basename(h[0])}:{h[1]}{'' if h[2] is None else ','+str(h[2])} [{h[3]}] {h[4][:120]}" for h in hits)
            if m >= n:
                verdict = "persists"
            elif m > 0:
                verdict = "persists_partial"
            else:
                verdict = "absent" if ran else "unverified"
        out.append({"repo": repo, "snippet_id": sid, "checker_id": cid, "key": key,
                    "verdict": verdict, "sliced_count": n, "full_count": m,
                    "original_file": of, "method": f"{r0['qualified_class_name']}.{r0['method_name']}",
                    "original_lines": f"{s}-{e}", "range_source": r0.get("range_source"), "module_check": mod_note,
                    "sliced_messages": " | ".join(sorted({x['sliced_message'] or '' for x in rs}))[:300],
                    "full_project_evidence": evidence})
    for r in not_compared:
        out.append({"repo": r["repo"], "snippet_id": r["snippet_id"], "checker_id": r["checker_id"],
                    "key": r.get("key"), "verdict": "not_compared", "sliced_count": 1, "full_count": "",
                    "original_file": r["original_file"],
                    "method": f"{r['qualified_class_name']}.{r['method_name']}",
                    "original_lines": f"{r['start']}-{r['end']}", "range_source": "", "module_check": r["reason"],
                    "sliced_messages": (r.get("sliced_message") or "")[:300], "full_project_evidence": ""})

    os.makedirs(os.path.dirname(os.path.abspath(out_csv)), exist_ok=True)
    with open(out_csv, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(out[0].keys()) if out else ["verdict"])
        w.writeheader()
        w.writerows(out)

    # ---------------- summary ----------------
    print(f"Sliced input: {a.run_dir}/stats/results.jsonl")
    print(f"  on-target warning rows: {len(rows)} in {len(groups)} (snippet, checker, key) groups;"
          f" not compared: {len(not_compared)}")
    if dup_records:
        print(f"  DUPLICATE records (same snippet+checker more than once; last one used): {len(dup_records)}")
        for (sid, cid), c in list(dup_records.items())[:10]:
            print(f"    {c}x {sid} [{cid}]")
    print("\nFull-project logs:")
    for (repo, cid), fl in sorted(logs.items(), key=lambda x: (str(x[0][0]), x[0][1])):
        if fl is None:
            print(f"  {repo:10} {cid:13} MISSING")
        else:
            print(f"  {repo:10} {cid:13} {len(fl.diags):6} unique diagnostics ({fl.raw} printed)  "
                  + ", ".join(os.path.basename(x) for x in fl.files))
    print("\nVerdicts per repo (one row per snippet+checker+key):")
    tab = collections.defaultdict(collections.Counter)
    for o in out:
        tab[o["repo"]][o["verdict"]] += 1
    cols = ["persists", "persists_partial", "absent", "unverified", "no_log", "not_compared"]
    print(f"  {'repo':12}" + "".join(f"{c:>17}" for c in cols))
    for repo in sorted(tab, key=str):
        print(f"  {str(repo):12}" + "".join(f"{tab[repo][c]:>17}" for c in cols))
    print(f"  {'TOTAL':12}" + "".join(f"{sum(t[c] for t in tab.values()):>17}" for c in cols))
    attention = [o for o in out if o["verdict"] in ("persists_partial", "unverified", "no_log")]
    if attention:
        print("\nNeeds attention (missing / partial):")
        for o in attention:
            print(f"  {o['verdict']:16} {o['snippet_id']} [{o['checker_id']}/{o['key']}] {o['sliced_count']}->{o['full_count']}  {o['module_check']}")
    rs = collections.Counter((o.get("range_source") or "").split(" (")[0].split(":")[0] for o in out if o["verdict"] != "not_compared")
    print("\nMethod line ranges: " + ", ".join(f"{k}: {v}" for k, v in rs.items()))
    amb = sum(1 for o in out if "AMBIGUOUS" in (o.get("range_source") or ""))
    if amb:
        print(f"  {amb} row(s) matched several overloads (union range used) - see range_source in the CSV")
    print(f"\nPer-row details: {out_csv}")


if __name__ == "__main__":
    main()
