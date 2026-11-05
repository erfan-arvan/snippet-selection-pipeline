#!/usr/bin/env python3
"""Join flagged_paths.csv with Locator's method-location output and config/pipeline.yaml's
per-repo url+commit, to produce one HTML row per flagged diagnostic with a hyperlink on the
method name pointing at its exact declaration line in the real GitHub source at the pinned
commit - not the sliced snippet, and not just the file (an actual #L<line> anchor).

Why this needs Locator.java at all: flagged_paths.csv's own original_start_line/
original_end_line columns are blank for every row checked so far, and diagnostic_line is the
line *inside the sliced snippet*, not the original file. Locator parses the real original
file (via javac's own parser - com.sun.source, a public, supported API; no --add-opens, no
classpath/dependencies needed since this never type-checks, only parses syntax) and reports
every method's exact line range, so the right one can be picked by (qualified class, method
name, parameter count) - param count comes from the snippet_id's own trailing __N suffix.

Usage (run on the machine where the repos-pinned clones and pipeline.yaml live):
  cd method-links
  javac Locator.java
  python3 build_links.py \
      /project/mjk76/ea442/snippet-selection-pipeline-output/legacy-import/stats/flagged_paths.csv \
      ../config/pipeline.yaml \
      links.html
"""
import csv
import html
import re
import subprocess
import sys
from pathlib import Path

CHUNK_SIZE = 150  # keep each `java Locator ...` argv comfortably under any ARG_MAX


def load_repo_table(pipeline_yaml_path):
    """Tiny regex parser for just the repo list's name/url/path/commit fields - avoids a
    PyYAML dependency on whatever bare `python3` this ends up being run with."""
    text = Path(pipeline_yaml_path).read_text()
    repos = {}
    current = None
    for line in text.splitlines():
        m = re.match(r"^\s*-\s*name:\s*(\S+)", line)
        if m:
            current = m.group(1)
            repos[current] = {}
            continue
        if current is None:
            continue
        if re.match(r"^\S", line):  # dedented back out of the repo list entirely
            current = None
            continue
        for key in ("url", "path", "commit"):
            m2 = re.match(rf"^\s*{key}:\s*(\S+)", line)
            if m2:
                repos[current][key] = m2.group(1)
    return repos


def github_owner_repo(url):
    m = re.search(r"github\.com/([^/]+)/([^/]+?)(?:\.git)?/?$", url)
    if not m:
        raise ValueError(f"not a recognizable github url: {url}")
    return m.group(1), m.group(2)


def strip_source_prefix(path):
    return path[len("source/"):] if path.startswith("source/") else path


def num_params_from_snippet_id(snippet_id):
    return int(snippet_id.rsplit("__", 1)[-1])


def run_locator(real_paths):
    """real_path -> list of (qualifiedClass, methodName, paramCount, startLine)."""
    by_file = {}
    for i in range(0, len(real_paths), CHUNK_SIZE):
        chunk = real_paths[i:i + CHUNK_SIZE]
        result = subprocess.run(["java", "Locator", *chunk], capture_output=True, text=True)
        if result.stderr:
            sys.stderr.write(result.stderr)
        for line in result.stdout.splitlines():
            parts = line.split("\t")
            if len(parts) != 6:
                continue
            f, qcls, mname, pcount, start_line, _end_line = parts
            by_file.setdefault(f, []).append((qcls, mname, int(pcount), int(start_line)))
    return by_file


def find_line(by_file, real_path, qualified_class_name, method_name, num_params):
    candidates = [
        s for (qcls, mname, pcount, s) in by_file.get(real_path, [])
        if qcls == qualified_class_name and mname == method_name and pcount == num_params
    ]
    return candidates[0] if len(candidates) == 1 else None


def main():
    if len(sys.argv) != 4:
        sys.exit(f"usage: {sys.argv[0]} <flagged_paths.csv> <pipeline.yaml> <out.html>")
    flagged_csv, pipeline_yaml, out_html = sys.argv[1:4]
    repos = load_repo_table(pipeline_yaml)

    with open(flagged_csv, newline="") as f:
        rows = list(csv.DictReader(f))

    file_pairs = sorted({(r["repo"], r["original_file"]) for r in rows if r["repo"] in repos})
    pair_to_real = {}
    for repo, original_file in file_pairs:
        repo_path = repos[repo].get("path")
        if repo_path:
            pair_to_real[(repo, original_file)] = str(Path(repo_path) / original_file)

    real_paths = sorted(set(pair_to_real.values()))
    print(f"Running Locator on {len(real_paths)} real file(s) ...", file=sys.stderr)
    by_file = run_locator(real_paths)

    out_rows = []
    located, unlocated = 0, 0
    for r in rows:
        repo = r["repo"]
        if repo not in repos or "url" not in repos[repo] or "commit" not in repos[repo]:
            out_rows.append((r, None))
            unlocated += 1
            continue
        owner, name = github_owner_repo(repos[repo]["url"])
        commit = repos[repo]["commit"]
        github_path = strip_source_prefix(r["original_file"])
        real_path = pair_to_real.get((repo, r["original_file"]))
        try:
            num_params = num_params_from_snippet_id(r["snippet_id"])
        except ValueError:
            num_params = None
        line = (
            find_line(by_file, real_path, r["qualified_class_name"], r["method_name"], num_params)
            if real_path and num_params is not None else None
        )
        base_url = f"https://github.com/{owner}/{name}/blob/{commit}/{github_path}"
        if line is None:
            unlocated += 1
            url = base_url
        else:
            located += 1
            url = f"{base_url}#L{line}"
        out_rows.append((r, url))

    cols = ["snippet_id", "checker_id", "status", "repo", "method_name", "key", "message",
            "diagnostic_line", "log_path"]
    with open(out_html, "w") as f:
        f.write("<!doctype html><meta charset='utf-8'><style>"
                "table{border-collapse:collapse;font:13px sans-serif} "
                "td,th{border:1px solid #ccc;padding:4px 8px;text-align:left;vertical-align:top} "
                "th{background:#4472C4;color:#fff;position:sticky;top:0}</style>")
        f.write(f"<p>{len(out_rows)} row(s) - {located} with an exact located line, "
                f"{unlocated} with only a file-level link (method not uniquely located; "
                f"check Locator's stderr output above for why).</p>")
        f.write("<table><tr>" + "".join(f"<th>{html.escape(c)}</th>" for c in cols) + "</tr>\n")
        for r, url in out_rows:
            f.write("<tr>")
            for c in cols:
                val = r.get(c, "")
                if c == "method_name" and url:
                    f.write(f"<td><a href='{html.escape(url)}' target='_blank'>{html.escape(val)}</a></td>")
                else:
                    f.write(f"<td>{html.escape(val)}</td>")
            f.write("</tr>\n")
        f.write("</table>")

    print(f"Wrote {out_html}: {len(out_rows)} rows, {located} located, {unlocated} not located.",
          file=sys.stderr)


if __name__ == "__main__":
    main()
