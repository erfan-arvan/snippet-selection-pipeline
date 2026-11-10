#!/usr/bin/env python3
"""Checker diagnostics inside one method of one file, from a full-project build log.
usage: evaluate.py <log> <repo-relative file> <start> <end> <key,key,...>
Prints one JSON object: target-key counts, all keys found in the method, and the matching lines."""
import collections, json, re, sys
log, f, start, end, keys = sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4]), sys.argv[5].split(",")
MAVEN = re.compile(r"^(?:\[(?:WARNING|ERROR)\]\s+)?(/\S+?\.java):\[(\d+),(\d+)\]\s+(?:(?:error|warning):\s+)?\[([\w.]+)\]\s*(.*)$")
JAVAC = re.compile(r"^(/\S+?\.java):(\d+):\s+(?:warning|error):\s+\[([\w.]+)\]\s*(.*)$")
seen = set()
for line in open(log, errors="replace"):
    line = line.rstrip("\n")
    m = MAVEN.match(line)
    if m:
        d = (m.group(1), int(m.group(2)), int(m.group(3)), m.group(4), m.group(5).strip())
    else:
        m = JAVAC.match(line)
        if not m:
            continue
        d = (m.group(1), int(m.group(2)), None, m.group(3), m.group(4).strip())
    if d[0].endswith("/" + f) and start <= d[1] <= end:
        seen.add(d)
allk = collections.Counter(d[3] for d in seen)
print(json.dumps({"target": {k: allk.get(k, 0) for k in keys}, "all_keys_in_method": dict(allk),
                  "lines": sorted(f"{d[1]}{'' if d[2] is None else ':' + str(d[2])} [{d[3]}] {d[4][:150]}" for d in seen)}))
