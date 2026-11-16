#!/usr/bin/env python3
"""List candidate methods from the warnings the checkers already produced on the ORIGINAL projects.

Mechanical narrowing only - the final false-positive / include decision is made by reading the code.
For every checker warning in the full-project logs:
  * find its enclosing method (Locator.java, on the pinned-commit clones),
  * skip test code, and methods the pipeline already sliced (in the run's stats/results.jsonl),
  * keep only methods that pass the selection criteria (the run's manifest/included.jsonl),
  * add triage notes (e.g. "index warning on a method parameter: likely needs an annotation").
Writes, under --out:
  candidates.csv   one row per (method, checker, key), most promising first
  candidates.txt   each candidate method's source with the warning lines marked (for reading)

With --write-run DIR it also writes DIR/manifest/candidates.jsonl: the included.jsonl records of
the most promising methods (no triage note, non-nullness first; at most --max-methods), so the
pipeline's own slice -> package -> check stages can be run on exactly those methods.

usage: mine_original_warnings.py [--run RUN_DIR] [--logs LOGS_DIR] [--clones CLONES_DIR] [--out OUT_DIR]
                                 [--write-run NEW_RUN_DIR] [--max-methods N]
"""
import argparse, collections, csv, json, os, re, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from compare_results import FullLog, gh_url, log_files  # noqa: E402

REPOS = ["apollo", "dubbo", "ghidra", "hudi", "mybatis-3", "netty"]
CHECKERS = ["nullness", "index", "interning", "resourceleak", "regex", "formatter"]
# Martin rejected every one of these as "needs annotation"; keep them, but rank them last.
LIKELY_ANNOTATION_NULLNESS = {"return", "override.param", "override.return"}


def param_names(src, st, en):
    """Parameter names from the method's signature text (up to its opening brace)."""
    sig = []
    for ln in range(st - 1, en):
        sig.append(src[ln])
        if "{" in src[ln] or src[ln].rstrip().endswith(";"):
            break
    text = re.sub(r"@\w+(\([^)]*\))?", " ", " ".join(sig))
    m = re.search(r"\((.*)\)", text.split("{", 1)[0])
    if not m:
        return set()
    names, depth, cur = [], 0, ""
    for ch in m.group(1):            # split on top-level commas (generics may contain commas)
        depth += ch in "<"; depth -= ch in ">"
        if ch == "," and depth == 0:
            names.append(cur); cur = ""
        else:
            cur += ch
    names.append(cur)
    return {re.findall(r"\w+", x)[-1] for x in names if re.findall(r"\w+", x)}


def param_is_index(line, pnames):
    """True if a parameter is itself an index/length/bound: a[p], a[p + 1], f(p), f(x, p), f(p, x).
    A parameter that only appears elsewhere on the line (e.g. pattern.substring(i + 1)) does not count."""
    alt = "|".join(map(re.escape, pnames))
    idx_methods = ("charAt|codePointAt|substring|subSequence|get|set|remove|add|arraycopy|copyOf|copyOfRange"
                   "|getByte|getShort|getInt|getLong|getChar|setByte|setShort|setInt|setLong|insert|deleteCharAt|setCharAt")
    return bool(re.search(r"\[\s*(?:" + alt + r")\s*(?:[-+]\s*\w+\s*)?\]", line) or
                re.search(r"\b(?:" + idx_methods + r")\s*\((?:[^()]*,)?\s*(?:" + alt + r")\s*[,)]", line))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", default="/project/mjk76/ea442/snippet-selection-pipeline-output/legacy-import")
    ap.add_argument("--logs", default="/project/mjk76/ea442/snippet-selection-pipeline-output/fullproject-verification")
    ap.add_argument("--clones", default="/scratch/mjk76/ea442/fullproject-verify-work")
    ap.add_argument("--out", default=None)
    ap.add_argument("--write-run", default=None)
    ap.add_argument("--max-methods", type=int, default=300)
    a = ap.parse_args()
    out_dir = a.out or os.path.join(a.logs, "mined")
    os.makedirs(out_dir, exist_ok=True)

    # methods that pass the selection criteria, and methods already sliced
    included = {}
    for line in open(os.path.join(a.run, "manifest", "included.jsonl")):
        if line.strip():
            r = json.loads(line)
            included[(r["project"], r["qualifiedClassName"].replace("$", "."), r["methodName"],
                      int(r.get("numParams", len(r.get("paramTypes", [])))))] = r
    processed = set()
    rj = os.path.join(a.run, "stats", "results.jsonl")
    if os.path.isfile(rj):
        for line in open(rj):
            if line.strip():
                processed.add(json.loads(line)["snippet_id"])

    rows, code = [], {}
    counts = collections.Counter()
    for repo in REPOS:
        root = os.path.join(a.clones, repo)
        if not os.path.isdir(root):
            print(f"WARNING: no clone at {root}; skipping {repo}", file=sys.stderr)
            continue
        for chk in CHECKERS:
            files = log_files(a.logs, repo, chk)
            if not files:
                continue
            fl = FullLog(files)
            restricted = any("FPV-ONLY-DEFS:" in open(f, errors="replace").read() for f in files)
            by_file = collections.defaultdict(list)
            for d in fl.diags:
                i = d[0].find("/" + repo + "/")
                rel = d[0][i + len(repo) + 2:] if i >= 0 else None
                if rel and "/src/test/" not in rel and os.path.isfile(os.path.join(root, rel)):
                    by_file[rel].append(d)
            methods = collections.defaultdict(list)
            rels = sorted(by_file)
            for k in range(0, len(rels), 200):
                p = subprocess.run(["java", os.path.join(HERE, "Locator.java")] + [os.path.join(root, r) for r in rels[k:k + 200]],
                                   capture_output=True, text=True)
                for l in p.stdout.splitlines():
                    f, cls, name, n, types, st, en = l.split("\t")
                    methods[os.path.relpath(f, root)].append((cls, name, int(n), types, int(st), int(en)))
            groups = collections.defaultdict(list)
            for rel, ds in by_file.items():
                for d in ds:
                    ms = [m for m in methods.get(rel, []) if m[4] <= d[1] <= m[5]]
                    if not ms:
                        continue
                    m = min(ms, key=lambda m: m[5] - m[4])          # innermost method
                    groups[(rel,) + m].append(d)
            for (rel, cls, name, n, types, st, en), ds in groups.items():
                counts[(repo, chk, "methods with warnings")] += 1
                sid = f"{repo}__{cls.replace('.', '_')}__{name}__{n}"
                if sid in processed:
                    counts[(repo, chk, "skipped: already sliced")] += 1
                    continue
                if (repo, cls, name, n) not in included:
                    counts[(repo, chk, "skipped: not in included.jsonl")] += 1
                    continue
                counts[(repo, chk, "kept")] += 1
                src = open(os.path.join(root, rel), errors="replace").read().splitlines()
                pnames = param_names(src, st, en) if n else set()
                for key, kd in sorted(collections.defaultdict(list, {k: [x for x in ds if x[3] == k] for k in {x[3] for x in ds}}).items()):
                    notes = []
                    if chk == "nullness" and key in LIKELY_ANNOTATION_NULLNESS:
                        notes.append("nullness return/override: likely needs annotation")
                    if chk == "index" and pnames and any(param_is_index(src[x[1] - 1], pnames) for x in kd):
                        notes.append("a method parameter is used directly as the index: likely needs an annotation")
                    if restricted:
                        notes.append("log was restricted (-AonlyDefs): this class may not have been fully checked")
                    rank = (1 if notes else 0, 0 if chk != "nullness" else 1)
                    rows.append(dict(rank=rank, record_key=(repo, cls, name, n), repo=repo, checker=chk, key=key, count=len(kd),
                                     method=f"{cls}.{name}", nparams=n, file=rel, lines=f"{st}-{en}",
                                     warning_lines=", ".join(str(x[1]) for x in kd),
                                     messages=" | ".join(sorted({x[4][:140] for x in kd})),
                                     notes="; ".join(notes), link=gh_url(repo, rel, st, en)))
                    code[(repo, cls, name, n)] = (rel, st, en, {x[1] for x in ds}, src)
    rows.sort(key=lambda r: (r["rank"], r["repo"], r["method"], r["checker"], r["key"]))
    cols = ["repo", "checker", "key", "count", "method", "nparams", "file", "lines", "warning_lines", "messages", "notes", "link"]
    with open(os.path.join(out_dir, "candidates.csv"), "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    seen = set()
    with open(os.path.join(out_dir, "candidates.txt"), "w") as f:
        for r in rows:
            k = (r["repo"],) + tuple(r["method"].rsplit(".", 1)) + (r["nparams"],)
            if k in seen or k not in code:
                continue
            seen.add(k)
            rel, st, en, wl, src = code[k]
            ks = [x for x in rows if (x["repo"], x["method"], x["nparams"]) == (r["repo"], r["method"], r["nparams"])]
            f.write(f"=== {r['repo']} | {r['method']} ({r['nparams']} params) | {rel}:{st}-{en}\n")
            for x in ks:
                f.write(f"--- {x['checker']} [{x['key']}] x{x['count']} at {x['warning_lines']}: {x['messages']}"
                        + (f"   ({x['notes']})" if x["notes"] else "") + "\n")
            for ln in range(st, en + 1):
                f.write(f"{'>>' if ln in wl else '  '}{ln:5} {src[ln - 1]}\n")
            f.write("\n")
    print("Per repo/checker:")
    for (repo, chk) in sorted({(k[0], k[1]) for k in counts}):
        c = {k[2]: v for k, v in counts.items() if k[:2] == (repo, chk)}
        print(f"  {repo:10} {chk:13} methods with warnings {c.get('methods with warnings', 0):5}  already sliced {c.get('skipped: already sliced', 0):4}"
              f"  not in criteria {c.get('skipped: not in included.jsonl', 0):5}  kept {c.get('kept', 0):4}")
    print(f"\n{len(rows)} candidate rows ({len(seen)} methods); {sum(1 for r in rows if not r['notes'])} without a triage note.")
    if a.write_run:
        picked = []
        for r in rows:                                 # rows are sorted most promising first
            if r["notes"] or r["record_key"] in picked:
                continue
            picked.append(r["record_key"])
            if len(picked) >= a.max_methods:
                break
        os.makedirs(os.path.join(a.write_run, "manifest"), exist_ok=True)
        cp = os.path.join(a.write_run, "manifest", "candidates.jsonl")
        with open(cp, "w") as f:
            for k in picked:
                f.write(json.dumps(included[k]) + "\n")
        print(f"\n{len(picked)} methods to slice -> {cp}")
        print("  by repo/checker of their best warning:",
              dict(collections.Counter((r["repo"], r["checker"]) for r in rows if r["record_key"] in set(picked) and not r["notes"])))
    print(f"  {out_dir}/candidates.csv\n  {out_dir}/candidates.txt")


if __name__ == "__main__":
    main()
