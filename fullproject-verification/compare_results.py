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
PIPELINE_YAML = os.path.join(HERE, "..", "config", "pipeline.yaml")


def load_repo_links(path=PIPELINE_YAML):
    """name -> (github url, pinned commit), from config/pipeline.yaml (no PyYAML needed)."""
    repos, cur = {}, None
    try:
        lines = open(path).read().splitlines()
    except OSError:
        return repos
    for line in lines:
        m = re.match(r"^\s*-\s*name:\s*(\S+)", line)
        if m:
            cur = m.group(1); repos[cur] = {}; continue
        if cur is None:
            continue
        if re.match(r"^\S", line):
            cur = None; continue
        m = re.match(r"^\s*(url|commit|path):\s*(\S+)", line)
        if m:
            repos[cur][m.group(1)] = m.group(2)
    global REPO_PATHS
    REPO_PATHS = {k: v["path"] for k, v in repos.items() if "path" in v}
    return {k: (v["url"].rstrip("/").removesuffix(".git"), v["commit"]) for k, v in repos.items() if "url" in v and "commit" in v}


REPO_PATHS = {}
REPO_LINKS = load_repo_links()


def repo_root(clones_root, repo):
    """Checkout used to read original sources: the verification clone, else the pipeline's own
    pinned checkout from config/pipeline.yaml (e.g. WxJava, which has no verification run)."""
    p = os.path.join(clones_root, str(repo))
    if os.path.isdir(p):
        return p
    return REPO_PATHS.get(repo, p)


def gh_url(repo, path, a, b=None):
    if repo not in REPO_LINKS or not path:
        return ""
    url, commit = REPO_LINKS[repo]
    if a is None:   # method lines unknown (e.g. no local clone): link the whole file
        return f"{url}/blob/{commit}/{path}"
    return f"{url}/blob/{commit}/{path}#L{a}" + (f"-L{b}" if b is not None and b != a else "")


def xl_link(url, label):
    """Excel turns =HYPERLINK(...) into a clickable cell when it opens the CSV (URL limit 255)."""
    if not url:
        return ""
    if len(url) > 255:
        return url
    return '=HYPERLINK("' + url + '","' + label.replace('"', "'") + '")'

# [WARNING] /abs/File.java:[12,34] [key] msg   (Maven; mybatis-3 prints [ERROR] ... error: [key];
#                                                some summary lines have no [LEVEL] prefix)
MAVEN_RE = re.compile(r"^(?:\[(?:WARNING|ERROR)\]\s+)?(/\S+?\.java):\[(\d+),(\d+)\]\s+(?:(?:error|warning):\s+)?\[([\w.]+)\]\s*(.*)$")
# /abs/File.java:12: warning: [key] msg           (javac via Gradle - ghidra)
JAVAC_RE = re.compile(r"^(/\S+?\.java):(\d+):\s+(?:warning|error):\s+\[([\w.]+)\]\s*(.*)$")
GRADLE_TASK_RE = re.compile(r"^> Task :([\w.-]+):(compile\w*Java)(?:\s+(\S.*))?$")

MEANING = {
    "persists": "Every occurrence of this warning in the slice is matched, one-to-one, to the same checker + key in the original method ON THE SAME STATEMENT (source text compared).",
    "persists_count_only": "The original method has this checker + key at least as often, but not every slice occurrence could be matched to the same statement - check by hand.",
    "persists_partial": "Reported in the original project, but fewer times than in the slice - check by hand.",
    "absent": "Not reported in the original project although the checker ran on this module - the warning exists only in the slice.",
    "unverified": "Not found, but there is no evidence the checker ran over this module (or the method's lines are unknown) - no conclusion.",
    "no_log": "No full-project run exists for this repo + checker.",
    "not_compared": "Not comparable: the sliced warning is not on the target method, or the slice did not compile.",
}


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
        base = {"snippet_id": sid, "checker_id": cid, "status": r["status"], "sliced_log": r.get("log_path"),
                "num_params": m and m.get("num_params"), "signature": m and m.get("target_method_signature"),
                "repo": m and m.get("repo"), "original_file": m and m.get("original_file"),
                "start": m and m.get("original_start_line"), "end": m and m.get("original_end_line"),
                "qualified_class_name": m and m.get("qualified_class_name"),
                "method_name": m and m.get("method_name"),
                "sliced_path": m and m.get("sliced_file") and os.path.join(run_dir, "snippets", sid, m["sliced_file"])}
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
                        if os.path.isfile(os.path.join(repo_root(clones_root, repo), *parts[i:]))), None)
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
        root = repo_root(clones_root, repo)
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
        if not os.path.isfile(os.path.join(repo_root(clones_root, key[0]), str(key[1]))):
            r["range_source"] = f"not found: no {repo_root(clones_root, key[0])}/{key[1]}"
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


_SRC = {}


def _lines(path):
    if path not in _SRC:
        try:
            _SRC[path] = open(path, errors="replace").read().splitlines()
        except (OSError, TypeError):
            _SRC[path] = None
    return _SRC[path]


def _norm(t):
    t = re.sub(r"//.*$", "", t)            # line comment
    return re.sub(r"\s+", "", t)


def _src(lines, ln):
    return lines[ln - 1].strip() if lines and 1 <= ln <= len(lines) else ""


def _window(lines, ln, k=3):
    if not lines:
        return ""
    return "".join(_norm(x) for x in lines[max(0, ln - 1 - k): ln + k])


def pair_by_statement(sliced_rows, hits, sliced_lines, orig_lines):
    """One-to-one pairing of sliced occurrences with original diagnostics that sit on the same
    statement: whitespace/comments ignored; Specimin may reflow a statement over different
    lines, so a line also matches when it is contained in the other side's +-3 line window.
    -> list of (sliced_row, hit or None, how)"""
    cand = []
    for i, r in enumerate(sliced_rows):
        st = _norm(_src(sliced_lines, r.get("sliced_line") or 0))
        for j, h in enumerate(hits):
            ot = _norm(_src(orig_lines, h[1]))
            if not st or not ot:
                continue
            if st == ot:
                score = 3
            elif len(st) >= 6 and st in _window(orig_lines, h[1]):
                score = 2
            elif len(ot) >= 6 and ot in _window(sliced_lines, r.get("sliced_line") or 0):
                score = 2
            else:
                continue
            if (r.get("sliced_message") or "").strip() == (h[4] or "").strip():
                score += 1
            cand.append((-score, i, j))
    cand.sort()
    used_i, used_j, pair = set(), set(), {}
    for neg, i, j in cand:
        if i in used_i or j in used_j:
            continue
        used_i.add(i); used_j.add(j); pair[i] = (j, "same line text" if -neg >= 3 else "same statement (reflowed)")
    return [(r, hits[pair[i][0]] if i in pair else None, pair[i][1] if i in pair else "") for i, r in enumerate(sliced_rows)]


def _orig_source(hits, pairs, orig_src):
    if not (orig_src and hits):
        return ""
    out = []
    for h in hits:
        tag = next((f"   <= slice L{r.get('sliced_line')} ({how})" for r, hh, how in pairs if hh is h), "   (not paired)")
        out.append(f"orig L{h[1]}: {_src(orig_src, h[1])}{tag}")
    return "\n".join(out)


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

    def in_method(self, original_file, start, end):
        """All checker diagnostics (any key) inside the method's lines."""
        out = []
        for path, ds in self.by_file.items():
            if path.endswith("/" + original_file):
                out += [d for d in ds if start <= d[1] <= end]
        return sorted(set(out), key=lambda d: (d[1], d[2] or 0))

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


SLICE_MEANING = {
    "identical": "Every warning of the slice is matched to the same statement in the original method, and the original method has no other warnings from this checker (same keys, same counts).",
    "count_only": "Same keys and counts as the original method, but at least one warning could not be matched to the same statement - check by hand.",
    "slice_warnings_all_in_original": "Every warning of the slice is in the original method, but the original method has additional warnings from this checker.",
    "differs": "At least one warning of the slice is missing (or occurs fewer times) in the original method.",
    "incomplete": "At least one warning could not be checked yet (no full-project log, or the checker did not demonstrably run on this module).",
}


def _fmt(counter):
    return "; ".join(f"{k} x{v}" for k, v in sorted(counter.items()))


def per_slice(out, groups, logs):
    """One row per (snippet, checker) that has on-target warnings."""
    rows = collections.OrderedDict()
    for o in out:
        if o["verdict"] == "not_compared":
            continue
        rows.setdefault((o["snippet_id"], o["checker_id"]), []).append(o)
    res = []
    for (sid, cid), os_ in rows.items():
        o0 = os_[0]
        sliced = collections.Counter({o["key"]: int(o["sliced_count"]) for o in os_})
        verdicts = {o["verdict"] for o in os_}
        orig = collections.Counter()
        fl = logs.get((o0["repo"], cid))
        lines = o0["original_method_lines"]
        if fl is not None and lines and "None" not in lines:
            st, en = (int(x) for x in lines.split("-"))
            for d in fl.in_method(o0["original_file"], st, en):
                orig[d[3]] += 1
        if verdicts & {"unverified", "no_log"}:
            status = "incomplete"
        elif verdicts & {"absent", "persists_partial"}:
            status = "differs"
        elif orig == sliced and verdicts == {"persists"}:
            status = "identical"
        elif orig == sliced:
            status = "count_only"
        else:
            status = "slice_warnings_all_in_original"
        res.append({"repo": o0["repo"], "snippet_id": sid, "checker_id": cid, "status": status,
                    "status_meaning": SLICE_MEANING[status], "method_link": o0["method_link"], "method": o0["method"],
                    "original_file": o0["original_file"], "original_method_lines": lines,
                    "slice_warnings": _fmt(sliced),
                    "original_method_warnings": _fmt(orig) if status != "incomplete" else "",
                    "only_in_slice": _fmt(sliced - orig) if status != "incomplete" else "",
                    "only_in_original": _fmt(orig - sliced) if status != "incomplete" else "",
                    "sliced_log": o0["sliced_log"], "full_project_log": o0["full_project_log"]})
    # snippet-level: identical for every checker that flagged it?
    allid = collections.defaultdict(lambda: True)
    for r in res:
        allid[r["snippet_id"]] &= r["status"] == "identical"
    for r in res:
        r["snippet_identical_for_all_checkers"] = "yes" if allid[r["snippet_id"]] else "no"
    order = {k: i for i, k in enumerate(SLICE_MEANING)}
    res.sort(key=lambda r: (order[r["status"]], str(r["repo"]), r["snippet_id"], r["checker_id"]))
    print("\nPer slice (snippet + checker):")
    c = collections.Counter(r["status"] for r in res)
    for k in SLICE_MEANING:
        print(f"  {k:32} {c[k]}")
    print(f"  snippets identical for ALL their checkers: {sum(1 for v in allid.values() if v)} of {len(allid)}")
    return res


def _xml(v):
    v = "" if v is None else str(v)
    v = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", v)
    return v.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def _col(i):
    n = ""
    while i:
        i, r = divmod(i - 1, 26)
        n = chr(65 + r) + n
    return n


def write_xlsx(path, out, tab, cols, by_slice=()):
    """Real .xlsx (standard library only): clickable links in *_link columns, bold frozen header,
    filters, wrapped text, one sheet per view."""
    import zipfile
    sheets = []
    summ = [["repo"] + cols] + [[str(r)] + [tab[r][c] for c in cols] for r in sorted(tab, key=str)]
    summ.append(["TOTAL"] + [sum(t[c] for t in tab.values()) for c in cols])
    summ += [[]] + [["verdict", "meaning"]] + [[k, v] for k, v in MEANING.items()]
    summ += [[]] + [["by-slice status", "meaning"]] + [[k, v] for k, v in SLICE_MEANING.items()]
    sheets.append(("Summary", summ, None))
    k = list(out[0].keys()) if out else []
    sheets.append(("All warnings", [k] + [[o.get(x) for x in k] for o in out], k))
    if by_slice:
        kb = list(by_slice[0].keys())
        sheets.append(("By slice", [kb] + [[r.get(x) for x in kb] for r in by_slice], kb))
    order = {v: i for i, v in enumerate(["absent", "persists_partial", "persists_count_only", "unverified", "no_log", "persists"])}
    res = sorted((o for o in out if o["verdict"] != "not_compared"),
                 key=lambda o: (order.get(o["verdict"], 9), str(o["repo"]), o["snippet_id"]))
    sheets.append(("Results", [k] + [[o.get(x) for x in k] for o in res], k))
    sheets.append(("Not compared", [k] + [[o.get(x) for x in k] for o in out if o["verdict"] == "not_compared"], k))
    widths = {"verdict_meaning": 50, "status_meaning": 50, "sliced_messages": 70, "full_project_messages": 70,
              "method": 55, "original_file": 55, "snippet_id": 55, "module_check": 40, "method_link": 30,
              "original_match_link": 30, "original_match_urls": 40, "full_project_log": 45, "sliced_log": 45,
              "slice_warnings": 35, "original_method_warnings": 35,
              "sliced_source": 70, "original_source": 80, "statement_match": 30}
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        ct = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
              '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">',
              '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>',
              '<Default Extension="xml" ContentType="application/xml"/>',
              '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>',
              '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>']
        ct += [f'<Override PartName="/xl/worksheets/sheet{i}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
               for i in range(1, len(sheets) + 1)]
        z.writestr("[Content_Types].xml", "".join(ct) + "</Types>")
        z.writestr("_rels/.rels", '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>')
        wb = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>']
        wb += [f'<sheet name="{_xml(n)}" sheetId="{i}" r:id="rId{i}"/>' for i, (n, _, _) in enumerate(sheets, 1)]
        dn = [f'<definedName name="_xlnm._FilterDatabase" localSheetId="{i-1}" hidden="1">\'{n}\'!$A$1:${_col(len(r[0]))}${len(r)}</definedName>'
              for i, (n, r, h) in enumerate(sheets, 1) if h and r and r[0]]
        z.writestr("xl/workbook.xml", "".join(wb) + "</sheets>" + (f"<definedNames>{''.join(dn)}</definedNames>" if dn else "") + "</workbook>")
        rels = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">']
        rels += [f'<Relationship Id="rId{i}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{i}.xml"/>'
                 for i in range(1, len(sheets) + 1)]
        rels.append(f'<Relationship Id="rId{len(sheets)+1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>')
        z.writestr("xl/_rels/workbook.xml.rels", "".join(rels) + "</Relationships>")
        # styles: 0 default, 1 bold header, 2 wrapped top-aligned, 3 blue underlined link
        z.writestr("xl/styles.xml", '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                   '<fonts count="3"><font><sz val="11"/><name val="Calibri"/></font><font><b/><sz val="11"/><name val="Calibri"/></font>'
                   '<font><u/><sz val="11"/><color rgb="FF0563C1"/><name val="Calibri"/></font></fonts>'
                   '<fills count="2"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill></fills>'
                   '<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>'
                   '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
                   '<cellXfs count="4"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>'
                   '<xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0" applyFont="1"/>'
                   '<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0" applyAlignment="1"><alignment wrapText="1" vertical="top"/></xf>'
                   '<xf numFmtId="0" fontId="2" fillId="0" borderId="0" xfId="0" applyFont="1" applyAlignment="1"><alignment vertical="top"/></xf></cellXfs>'
                   '<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles></styleSheet>')
        for i, (name, rows, header) in enumerate(sheets, 1):
            links, xml = [], []
            ncol = max((len(r) for r in rows), default=1)
            for ri, row in enumerate(rows, 1):
                cells = []
                for ci, v in enumerate(row, 1):
                    ref = f"{_col(ci)}{ri}"
                    if v is None or v == "":
                        continue
                    colname = header[ci - 1] if header and ri > 1 else ""
                    if isinstance(v, (int, float)) and not isinstance(v, bool):
                        cells.append(f'<c r="{ref}" s="{1 if ri == 1 else 2}"><v>{v}</v></c>')
                        continue
                    v = str(v)
                    style = 1 if ri == 1 else 2
                    if colname.endswith("_link") and v.startswith("http"):
                        links.append((ref, v))
                        style, v = 3, v.rsplit("/", 1)[-1]
                    cells.append(f'<c r="{ref}" t="inlineStr" s="{style}"><is><t xml:space="preserve">{_xml(v[:32000])}</t></is></c>')
                xml.append(f'<row r="{ri}">{"".join(cells)}</row>')
            hdr = rows[0] if rows else []
            colw = "".join(f'<col min="{c}" max="{c}" width="{widths.get(str(hdr[c-1]) if header else "", 22 if not header else 16)}" customWidth="1"/>'
                           for c in range(1, ncol + 1))
            sheet = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">',
                     '<sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/></sheetView></sheetViews>',
                     f"<cols>{colw}</cols>", f"<sheetData>{''.join(xml)}</sheetData>"]
            if header and len(rows) > 0:
                sheet.append(f'<autoFilter ref="A1:{_col(ncol)}{len(rows)}"/>')
            if links:
                sheet.append("<hyperlinks>" + "".join(f'<hyperlink ref="{r}" r:id="rId{j}"/>' for j, (r, _) in enumerate(links, 1)) + "</hyperlinks>")
                z.writestr(f"xl/worksheets/_rels/sheet{i}.xml.rels",
                           '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                           + "".join(f'<Relationship Id="rId{j}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink" Target="{_xml(u)}" TargetMode="External"/>'
                                     for j, (_, u) in enumerate(links, 1)) + "</Relationships>")
            z.writestr(f"xl/worksheets/sheet{i}.xml", "".join(sheet) + "</worksheet>")


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
    locate_ranges(rows + not_compared, a.clones)

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
        hits, pairs, sl_src, orig_src = [], [], None, None
        if fl is None:
            verdict, m, evidence, mod_note = "no_log", 0, "", f"no log under {a.logs}/{repo}/ for {cid}"
        elif s is None or e is None:
            verdict, m, evidence, mod_note = "unverified", 0, "", f"method range unknown: {r0['range_source']}"
        else:
            hits = fl.matches(of, key, s, e)
            m = len(hits)
            ran, mod_note = fl.module_evidence(of)
            evidence = " | ".join(f"{os.path.basename(h[0])}:{h[1]}{'' if h[2] is None else ','+str(h[2])} [{h[3]}] {h[4][:120]}" for h in hits)
            orig_src = _lines(os.path.join(repo_root(a.clones, repo), of)) if of else None
            sl_src = _lines(r0.get("sliced_path"))
            pairs = pair_by_statement(rs, hits, sl_src, orig_src)
            k = sum(1 for _, h, _ in pairs if h is not None)
            if m >= n and k == n:
                verdict = "persists"
            elif m >= n:
                verdict = "persists_count_only"
            elif m > 0:
                verdict = "persists_partial"
            else:
                verdict = "absent" if ran else "unverified"
        fname = os.path.basename(of or "")
        murl = gh_url(repo, of, s, e)
        hurls = [gh_url(repo, of, h[1]) for h in hits]
        out.append({"repo": repo, "snippet_id": sid, "checker_id": cid, "key": key,
                    "verdict": verdict, "verdict_meaning": MEANING[verdict],
                    "method_link": murl,
                    "original_match_link": hurls[0] if hurls else "",
                    "original_match_urls": "\n".join(hurls),
                    "sliced_count": n, "full_count": m,
                    "method": f"{r0['qualified_class_name']}.{r0['method_name']}",
                    "original_file": of, "original_method_lines": f"{s}-{e}",
                    "method_lines_source": r0.get("range_source"),
                    "sliced_lines": ", ".join(str(x.get("sliced_line")) for x in rs),
                    "sliced_messages": "\n".join(f"line {x.get('sliced_line')}: {x.get('sliced_message') or ''}" for x in rs),
                    "full_project_lines": ", ".join(f"{h[1]}" + ("" if h[2] is None else f":{h[2]}") for h in hits) if fl is not None and s is not None else "",
                    "full_project_messages": "\n".join(f"{h[1]}{'' if h[2] is None else ':'+str(h[2])} [{h[3]}] {h[4]}" for h in hits) if fl is not None and s is not None else "",
                    "statement_match": (f"{sum(1 for _, h, _ in pairs if h is not None)} of {n} matched to the same statement"
                                        + ("" if sl_src else " (sliced source file not found)") + ("" if orig_src else " (original source file not found)"))
                                       if pairs else "",
                    "sliced_source": "\n".join(f"slice L{x.get('sliced_line')}: {_src(sl_src, x.get('sliced_line') or 0)}" for x in rs) if sl_src else "",
                    "original_source": _orig_source(hits, pairs, orig_src),
                    "module_check": mod_note,
                    "full_project_log": ", ".join(fl.files) if fl is not None else "",
                    "sliced_log": r0.get("sliced_log") or ""})
    for r in not_compared:
        out.append({"repo": r["repo"], "snippet_id": r["snippet_id"], "checker_id": r["checker_id"],
                    "key": r.get("key"), "verdict": "not_compared", "verdict_meaning": MEANING["not_compared"],
                    "method_link": gh_url(r["repo"], r["original_file"], r.get("start"), r.get("end")),
                    "original_match_link": "", "original_match_urls": "",
                    "sliced_count": 1, "full_count": "",
                    "method": f"{r['qualified_class_name']}.{r['method_name']}",
                    "original_file": r["original_file"],
                    "original_method_lines": f"{r.get('start')}-{r.get('end')}" if r.get("start") is not None else "",
                    "method_lines_source": r.get("range_source") or "", "sliced_lines": str(r.get("sliced_line") or ""),
                    "sliced_messages": r.get("sliced_message") or "", "full_project_lines": "",
                    "full_project_messages": "", "statement_match": "", "sliced_source": "", "original_source": "",
                    "module_check": r["reason"], "full_project_log": "",
                    "sliced_log": r.get("sliced_log") or ""})

    by_slice = per_slice(out, groups, logs)
    os.makedirs(os.path.dirname(os.path.abspath(out_csv)), exist_ok=True)
    slice_csv = os.path.splitext(out_csv)[0] + "_by_slice.csv"
    with open(slice_csv, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(by_slice[0].keys()) if by_slice else ["status"])
        w.writeheader()
        w.writerows(by_slice)
    with open(out_csv, "w", newline="", encoding="utf-8-sig") as f:
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
    cols = ["persists", "persists_count_only", "persists_partial", "absent", "unverified", "no_log", "not_compared"]
    print(f"  {'repo':12}" + "".join(f"{c:>17}" for c in cols))
    for repo in sorted(tab, key=str):
        print(f"  {str(repo):12}" + "".join(f"{tab[repo][c]:>17}" for c in cols))
    print(f"  {'TOTAL':12}" + "".join(f"{sum(t[c] for t in tab.values()):>17}" for c in cols))
    attention = [o for o in out if o["verdict"] in ("persists_partial", "persists_count_only", "unverified", "no_log")]
    if attention:
        print("\nNeeds attention (missing / partial):")
        for o in attention:
            print(f"  {o['verdict']:16} {o['snippet_id']} [{o['checker_id']}/{o['key']}] {o['sliced_count']}->{o['full_count']}  {o['module_check']}")
    xlsx = os.path.splitext(out_csv)[0] + ".xlsx"
    write_xlsx(xlsx, out, tab, cols, by_slice)
    print(f"Spreadsheet (clickable links): {xlsx}")
    rs = collections.Counter((o.get("method_lines_source") or "").split(" (")[0].split(":")[0] for o in out if o["verdict"] != "not_compared")
    print("\nMethod line ranges: " + ", ".join(f"{k}: {v}" for k, v in rs.items()))
    amb = sum(1 for o in out if "AMBIGUOUS" in (o.get("method_lines_source") or ""))
    if amb:
        print(f"  {amb} row(s) matched several overloads (union range used) - see range_source in the CSV")
    print(f"\nPer-row details: {out_csv}")
    print(f"Per slice:       {slice_csv}")


if __name__ == "__main__":
    main()
