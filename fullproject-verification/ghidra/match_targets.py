#!/usr/bin/env python3
"""
Match target diagnostics from the manifest against a full-module build log.

usage:
  python3 -I match_targets.py <manifest.json> <ghidra_clone_dir> <checker_id> <build_log> [--csv out.csv] [--append]

Method attribution: Locator.java (JDK compiler tree API, needs JDK >= 21 on PATH)
parses each target source file and gives exact [start,end] line ranges of every
method/constructor, with qualified class names including nested classes. A
build warning "<file>:<line>: warning: [<key>] ..." is a HIT for a target when
file and key match and the line lies inside a method named `method_name` of
`qualified_class_name` (or a class nested in it). Lambdas / anonymous classes
inside the method count as the method.

Targets sharing (snippet_id, key) are matched as a multiset:
  hits >= n           -> confirmed_persists for all n
  0 < hits < n        -> first `hits` confirmed_persists, rest flagged
                         confirmed_artifact with a "fewer occurrences" note
                         (REVIEW THESE BY HAND)
  hits == 0           -> confirmed_artifact, but ONLY if the module's compile
                         task actually executed and did not FAIL; otherwise
                         could_not_verify
"""
import json, sys, re, subprocess, collections, csv, os

args = [a for a in sys.argv[1:] if not a.startswith('--')]
manifest, G, cid, logf = args[:4]
csv_out = sys.argv[sys.argv.index('--csv') + 1] if '--csv' in sys.argv else None
if csv_out and csv_out in args: args.remove(csv_out)
G = os.path.abspath(G).rstrip('/') + '/'
HERE = os.path.dirname(os.path.abspath(__file__))

d = json.load(open(manifest))
tg = [t for t in d['target_diagnostics'] if t['checker_id'] == cid]
if not tg: sys.exit(f'no targets for checker {cid}')

def module_task(path):
    name = path.split('/src/')[0].split('/')[-1]
    return f':{name}:compileDmgJava' if name == 'DMG' else f':{name}:compileJava'

log = open(logf, errors='replace').read().splitlines()
WARN = re.compile(r'^(/\S+\.java):(\d+): (warning|error): \[([\w.]+)\] (.*)$')
warns = []
for i, line in enumerate(log):
    m = WARN.match(line)
    if m and m.group(1).startswith(G):
        warns.append((m.group(1)[len(G):], int(m.group(2)), m.group(4), m.group(5)))

def task_state(task):
    st = None
    for line in log:
        if line.startswith('> Task ' + task):
            rest = line[len('> Task ' + task):].strip()
            st = rest or 'EXECUTED'
    return st  # None = never ran

files = sorted({t['original_file'] for t in tg})
loc = subprocess.run(['java', os.path.join(HERE, 'Locator.java')] + [G + f for f in files],
                     capture_output=True, text=True, check=True).stdout
methods = collections.defaultdict(list)
for line in loc.splitlines():
    f, c, n, s, e = line.split('\t')
    methods[f[len(G):]].append((c, n, int(s), int(e)))

groups = collections.OrderedDict()
for t in tg:
    groups.setdefault((t['snippet_id'], t['key']), []).append(t)

rows = []
for (sid, key), ts in groups.items():
    t = ts[0]
    q = t['qualified_class_name']
    ms = [m for m in methods[t['original_file']] if m[1] == t['method_name'] and (m[0] == q or m[0].startswith(q + '.'))]
    if any(m[0] == q for m in ms): ms = [m for m in ms if m[0] == q]
    hits = [w for w in warns if w[0] == t['original_file'] and w[2] == key and any(s <= w[1] <= e for _, _, s, e in ms)]
    task = module_task(t['original_file'])
    state = task_state(task)
    fname = os.path.basename(t['original_file'])
    for i, _t in enumerate(ts):
        if not ms:
            res, ev = 'could_not_verify', f"method {t['method_name']} not found in {q} at the pinned commit (Locator found no such method)."
        elif i < len(hits):
            w = hits[i]
            res, ev = 'confirmed_persists', f"Full {task} build: {fname}:{w[1]}: warning: [{w[2]}] {w[3]}"
        elif state is None or 'FAILED' in state or state in ('UP-TO-DATE', 'FROM-CACHE', 'SKIPPED', 'NO-SOURCE'):
            res, ev = 'could_not_verify', f"{task} state={state or 'never ran'}; no checker signal for this module."
        elif hits:
            res, ev = 'confirmed_artifact', (f"Full {task} build emitted only {len(hits)} [{key}] warning(s) in "
                                             f"{t['method_name']} vs {len(ts)} in slice; this extra occurrence did not reproduce. REVIEW.")
        else:
            res, ev = 'confirmed_artifact', (f"Full {task} build completed (task {state}) with no [{key}] warning in "
                                             f"{q}.{t['method_name']} (lines {ms[0][2]}-{ms[0][3]}).")
        rows.append([sid, cid, key, res, ev])
        print(res.ljust(19), sid, key, '|', ev[:160])

if csv_out:
    new = not os.path.exists(csv_out) or '--append' not in sys.argv
    with open(csv_out, 'w' if new else 'a', newline='') as fh:
        w = csv.writer(fh)
        if new: w.writerow(['snippet_id', 'checker_id', 'key', 'result', 'evidence'])
        w.writerows(rows)
print(collections.Counter(r[3] for r in rows), 'warnings parsed from log:', len(warns))
