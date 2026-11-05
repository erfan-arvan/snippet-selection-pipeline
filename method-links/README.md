# Method links for flagged diagnostics

Builds one HTML row per row of `legacy-import/stats/flagged_paths.csv`, with a hyperlink on
the method name pointing at that method's exact declaration line in the real GitHub source
at the pinned commit - e.g.
`https://github.com/NationalSecurityAgency/ghidra/blob/93c19e3cc6733fab119ace63a39be2aec89208b3/Ghidra/Features/Base/src/main/java/ghidra/app/util/headless/AnalyzeHeadless.java#L559`.

## Why this needs a real parser, not just the CSV

`flagged_paths.csv`'s own `original_start_line`/`original_end_line` columns are blank for
every row checked so far, and `diagnostic_line` is the line *inside the sliced snippet*, not
the original file. `original_file` also carries a `source/` prefix that is a local staging
symlink name (`staging_dir/"source"` -> the real repo clone, see
`orchestrator/snippet_pipeline/classpath.py`), not part of the real GitHub path - strip it for
the URL, but keep it to find the file on disk under each repo's `path` in `pipeline.yaml`.

`Locator.java` parses the real original file with javac's own public parser API
(`com.sun.source` - a pure syntax parse via `task.parse()`, never `.analyze()`, so it needs no
classpath/dependencies and works on any of the 6 repos' files) and reports every method's
exact line range. `build_links.py` then picks the right overload by (qualified class name,
method name, parameter count) - parameter count comes from the snippet_id's own trailing
`__N` suffix, not from re-parsing a signature string.

## Running it (on Wulver, where the repo clones and pipeline.yaml live)

```bash
cd method-links
javac Locator.java
python3 build_links.py \
    /project/mjk76/ea442/snippet-selection-pipeline-output/legacy-import/stats/flagged_paths.csv \
    ../config/pipeline.yaml \
    links.html
```

Needs a JDK on `PATH` (`module load Java/17.0.15` or `Java/23.0.2`; either works - this only
parses syntax, so the JDK minor version doesn't matter the way it does for the Checker
Framework). Pure stdlib Python 3, no pip install needed.

Open `links.html` in a browser (download it off HPC first, however you normally pull files
off `/project/mjk76/ea442/...`). The one-line summary at the top says how many rows got an
exact `#L<line>` anchor vs. a file-only link (method not uniquely locatable - check the
javac stderr output the script prints while running for why, usually a parse error on that
specific file).
