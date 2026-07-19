# snippet-selection-pipeline

Implements **Phase 1** of the snippet-selection methodology from §9.3 of the proposal
("Snippet Selection and Construction"): given a set of already-selected open-source
repositories, this pipeline

1. resolves each repo's real dependency classpath,
2. filters candidate methods against the six §9.3 inclusion criteria,
3. slices each surviving candidate into a minimized program with
   [Specimin](https://github.com/njit-jerse/specimin),
4. packages each slice as a standalone, buildable Gradle project, and
5. runs a configurable set of Checker Framework checkers against each snippet project,
   recording which produce a warning on the target method (candidates for the paper's manual
   real-defect-vs-false-positive triage) versus which pass clean.

It does **not** attempt the paper's Phase 4 "Verifiability-Controlled Construction"
transformations (eliminating/injecting false positives) - that's a human-in-the-loop step
downstream of this pipeline's stats output.

## Repository layout

```
config/
  pipeline.yaml        # repos, tool paths, checker-framework version, output location
  checkers.yaml         # the 9 Checker Framework checkers Stage F runs
tools/
  method-analyzer/       # extended fork of MethodAnalyzerApp (method filtering, JavaParser-based)
orchestrator/
  snippet_pipeline/      # the Python CLI that drives everything
  templates/              # Jinja2 template for each snippet's build.gradle.kts
tests/                    # pytest (orchestrator logic) - Java tests live in tools/method-analyzer/src/test
```

## Prerequisites

- **JDK 17+** and a **Gradle 8.x** on `PATH` (or set `gradle_command` in `pipeline.yaml` to a
  wrapper script).
- **Python 3.10+**.
- A local clone of [njit-jerse/specimin](https://github.com/njit-jerse/specimin) - set
  `tools.specimin_dir` in `pipeline.yaml` to it. It's built automatically the first time
  Stage D invokes it (via `gradle run`), but you can `cd` in and `gradle build` yourself first
  to confirm it compiles in your environment.
- Local clones of whichever of the 16 target repos you want to run against, with `path` (and
  ideally `commit`, for reproducibility) filled in per repo in `config/pipeline.yaml`. The
  pipeline never clones anything itself.

## Setup

```sh
cd orchestrator
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

`tools/method-analyzer`'s fat jar is built automatically the first time you run the `filter`
stage (via `gradle shadowJar`), or build it yourself ahead of time:

```sh
cd tools/method-analyzer
gradle shadowJar
```

## Running

Each stage is a separate CLI invocation; `filter` is the entry point - it mints a run id and
records it as "the most recent run" so later stages (each a fresh process) find the same
output directory without you having to pass it around manually. Use `--run-id` to target a
specific run explicitly (e.g. to re-run `check` against an older `slice`/`package` output).

```sh
snippet-pipeline -c ../config/pipeline.yaml filter    # Stage A+B: classpath + method filtering
snippet-pipeline -c ../config/pipeline.yaml select    # Stage C:   candidate selection
snippet-pipeline -c ../config/pipeline.yaml slice     # Stage D:   Specimin slicing
snippet-pipeline -c ../config/pipeline.yaml package   # Stage E:   package as Gradle modules
snippet-pipeline -c ../config/pipeline.yaml check     # Stage F+G: run checkers, print stats

# or, all five in sequence:
snippet-pipeline -c ../config/pipeline.yaml all
```

Output for a run lands under `output_dir/<run-id>/`:

```
repos_staging/<repo>/          # symlink to your real clone + .pipeline-classpath.txt / .pipeline-sourceroot.txt
manifest/manifest.jsonl        # every candidate method, with full per-criterion detail
manifest/candidates.jsonl      # only methods passing all six criteria
slices/<snippet-id>/           # raw Specimin output per candidate
snippets/<snippet-id>/         # each candidate packaged as a standalone Gradle project
logs/                          # method-analyzer, slice, and checker logs - every raw run is kept
stats/results.csv, results.jsonl  # one row per (snippet, checker): status + log_path
```

`check`'s console summary always prints the run's log directory and the log path for every
`flagged`/`slice_suspect` row, so any result can be traced back to the exact raw run that
produced it without re-running anything.

## The six filtering criteria (§9.3)

Implemented in `tools/method-analyzer`'s `MethodExtractor`/`JdkOnlyTypeChecker`:

1. All types in the signature **and body** are JDK-only - checked via real type resolution
   (param/return/local-variable types, and the resolved type *and declaring type* of every
   expression that can introduce a dependency), not just "does this override a `java.*`
   method". A call to a project-internal helper with a JDK-typed signature (e.g. `int ->
   int`) still fails this criterion, because the *declaring* type is checked separately from
   the *return* type. Anything that fails to resolve is treated as non-JDK (fails closed).
2. No annotations on the method signature.
3. `static` modifier present.
4. Has a Javadoc comment.
5. At least one parameter, non-void return.
6. 20-30 non-blank, non-comment lines of code.

Every candidate method - not just the ones that pass - is written to the manifest with its
full per-criterion breakdown, so rejections stay debuggable.

## Known limitations (read before running at scale)

- **Classpath resolution is generic and best-effort.** `classpath.py` unions the compile
  classpath across every Gradle/Maven module it can find in a repo, rather than mapping each
  candidate file to its owning module's exact classpath. This is strictly more permissive
  than a precise per-module classpath - occasionally it could let an ambiguous symbol resolve
  that a tighter classpath wouldn't - but it never removes a jar a module actually needs, so
  it fails safe with respect to criterion (1)'s "unresolved ⇒ not JDK" rule.
  - **Selenium builds with Bazel**, which neither the Gradle nor Maven resolution path
    supports. Supply a `classpath_override` file (one jar path per line) for it, or exclude
    it from the run.
  - **javaguide** is primarily a Markdown study-notes repository, not a buildable Java
    project - expect few or no candidates from it.
- **Specimin's output is for static analysis, not execution**, by its own documentation: any
  non-target method reachable from the target gets its body replaced with `throw new
  Error()`. Criterion (1) should mean a target method never calls back into other
  project-internal methods, so this normally shouldn't happen - but it isn't a hard guarantee
  (e.g. a call to a project-internal method whose *own* signature happens to be JDK-typed
  would still pass criterion 1's per-call checks yet still get stubbed by Specimin if it
  isn't itself a target). Stage E's packaging step scans every sliced file for `throw new
  Error()` and records any hits in `snippet.json`'s `stub_body_warnings` as a safety net -
  check that list before treating a "passed" snippet as genuinely runnable.
- **Checker Framework / Gradle plugin versions**: `config/pipeline.yaml`'s
  `checker_framework.version` (4.2.1) and `gradle_plugin_version` (0.6.42) were the current
  releases as of this pipeline's authoring and have been exercised end-to-end against a real
  snippet project in this environment - the plugin resolves, `checkerFramework { checkers =
  ... }` applies the requested checker, and the Checker Framework version is pinned
  explicitly via the `compileOnly("org.checkerframework:checker-qual:...")` /
  `checkerFramework("org.checkerframework:checker:...")` dependency declarations (not a
  plugin-level `checkerFrameworkVersion` property - that doesn't exist in this plugin's DSL).
  Both ship frequently; re-verify against
  [the plugin's Gradle Portal page](https://plugins.gradle.org/plugin/org.checkerframework)
  and [Checker Framework's releases](https://github.com/typetools/checker-framework/releases)
  before a long run.
- **No redundancy/dedup pass yet** across near-identical methods (the earlier pilot study's
  `atan2`/`atan2Deg` situation) - deferred until real candidate volume across the 16 repos is
  visible.
- **Checker isolation**: each (snippet, checker) pair runs as its own `gradle clean
  compileJava -PcheckerClass=...` invocation, never combining multiple checkers in one
  compile, so a diagnostic is always attributable to exactly one checker. `clean` is required
  before every run - without it, Gradle's up-to-date checks can skip `compileJava` entirely
  since the checker-class property isn't a tracked task input, which would silently reuse a
  previous checker's result.

## What's been verified in this environment vs. not

Verified end-to-end against a real (small, synthetic) fixture with the real tools: full
JavaParser-based six-criteria filtering (including the JDK-declaring-type edge case), real
Specimin invocation and output, real packaging into a Gradle module, and real Checker
Framework runs producing both a clean pass and a genuine flagged diagnostic (an
`array.access.unsafe.low` from the Index Checker), correctly attributed to the target
method's line range. All pytest/JUnit tests pass.

**Not** exercised here: an actual run against the 16 real target repos (Netty, Kafka, etc.) -
they aren't available in this environment, and cloning + building all of them is a
multi-hour, multi-GB operation you'll want to run yourself. Expect to iterate on
`classpath.py`'s module-discovery heuristics once you see real (especially multi-module)
repo layouts.
