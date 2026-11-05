# Full-project checker verification

Checks whether each warning flagged on a *sliced* snippet (Specimin's output) also appears
when the same Checker Framework checker is run on the **real, full, unsliced project** at the
same pinned commit. A warning that disappears with full context is a confirmed slicing
artifact; a warning that persists is not caused by slicing.

Per repo: `patches/` (one diff per checker, sometimes per submodule), a `run_*.sh` script that
applies the right patch, runs the real build (Maven or Gradle, whichever that repo actually
uses) with that one checker enabled, and always reverts the patch afterward, plus a `README.md`
with that repo's own gotchas.

## Status by repo

| Repo | Patches | Validated with a real passing build? | Comparison done? |
|---|---|---|---|
| apollo | 1 (nullness) | Yes, confirmed twice | 2/2 — `results_apollo.csv` |
| mybatis-3 | 2 (interning, nullness) | Yes, confirmed twice | 6/6 — `results_mybatis-3.csv` |
| netty | 11 (4 checkers x submodules) | Yes, all 4 checkers incl. nullness on all 6 submodules (2026-11-05, via `submit_verify_light.sh`) | 25 attempted, 6 unreached — `results_netty.csv` |
| dubbo | 12 (2 checkers x submodules) | Yes, index and nullness on all 6 modules (2026-11-05, after the `!dubbo-maven-plugin` fix) | 26 attempted, 4 unreached — `results_dubbo.csv` |
| ghidra | 5 (1 per checker) | Only regex + resourceleak confirmed; index/nullness/interning unrun | 2/114 — `ghidra/validated_results_partial.csv` |
| hudi | 4 (formatter, index, nullness, regex) | **Not validated at all** — treat first HPC run as the real first test | none |

## Build tools on Wulver

- apollo, mybatis-3, netty, dubbo, hudi: one Maven 3.9.9 at `/scratch/mjk76/ea442/apache-maven-3.9.9`, downloaded there if it is missing (`lib.sh` `setup_maven`). The jobs don't use the repos' own `./mvnw`: apollo's wrapper pins Maven 3.5.4, mybatis-3's and dubbo's download their wrapper jar at run time, and the patches were validated with Maven 3.9.x. The run scripts still fall back to `./mvnw` if `MVN` is unset. JDK: `Java/17.0.15`.
- ghidra: its own `./gradlew` (Gradle 8.12.1, via `Ghidra/RuntimeScripts/Common/support/gradle/gradle-wrapper.jar`). JDK: `Java/23.0.2`, because ghidra needs >= 21 and Wulver has no 21.

Maven local repos: the light job uses `/scratch/mjk76/ea442/.m2-fpverify-light` and the hudi job uses `/scratch/mjk76/ea442/.m2-fpverify-hudi`. They are separate so the two jobs can run at the same time without writing into one local repo concurrently. The run scripts read the path from `M2_REPO`.

## No diagnostics are truncated or silently dropped

Two separate javac-level caps could otherwise lose diagnostics needed for the diff, and both
are already overridden in every checker patch for every repo:

- **`-Xmaxerrs 100` / `-Xmaxwarns 100`** — javac's own built-in default caps on how many errors
  or warnings it will print, regardless of build tool. Every patch (`apollo`, `mybatis-3`,
  `netty`, `dubbo`, `ghidra`, `hudi`) sets both to `10000` explicitly in `compilerArgs`/
  `compilerArgs +=`, so no diagnostic past the 100th is ever dropped.
- **Maven/Gradle reactor abort on first module failure** — in a multi-submodule build
  (`-pl A,B,C -am`), if one module hard-fails, Maven/Gradle by default stops before building
  the rest, silently losing every diagnostic in the modules after it. `-Awarns` (already set
  everywhere except mybatis-3, which is single-module and doesn't need it) turns checker
  findings into warnings so they don't trigger this at all; `run_*.sh`'s `mvn` calls now also
  pass `-fae` (fail-at-end) as a second safety net, and `run_ghidra_checker.sh`'s gradle call
  already used `--continue` — so even an unrelated real failure in one module won't cut off
  diagnostics from the rest of the set.

Maven does print each warning twice in its summary (see each repo's own README for the
`sort -u` note) — a cosmetic duplication in the console output, not a loss — and the full,
untruncated text of every diagnostic is always in the log file this script writes, which is
what the actual diff should be run against, not the printed "N diagnostics" one-line count
(that count's regex can undercount; the log file is authoritative).

## Watching progress while it runs

Every build command in every `run_*.sh` streams Maven/Gradle's real output live (via `tee`),
not just into its own per-checker log file — so SLURM's own `%x.%j.out` file shows the actual
compile/download output as it happens, not just silence until the step finishes. Each submit
script also prints a timestamped `[YYYY-MM-DD HH:MM:SS] === step ===` banner before every
repo/checker it starts. So once a job is running:

```
tail -f fpverify-light.<jobid>.out      # or fpverify-hudi./fpverify-ghidra.
```

shows, in order: which repo/checker is currently running and when it started, then that
build's live Maven/Gradle output, then its `mvn/gradle exit=...` and diagnostic-count summary
line, then the next step's banner — so a long job (ghidra's 72h one especially) can be told
apart as "still compiling module N" vs. actually stuck, without waiting for it to finish. The
same content also lands in each checker's own `.log` file under `$OUT` for grepping afterward.

## Running on HPC

Submit from the repo root, i.e. `/project/mjk76/ea442/snippet-selection-pipeline`. The three jobs are independent and can run at the same time.

- `submit_verify_light.sh`: apollo, mybatis-3, netty and dubbo, in that order. 24 h limit.
- `submit_verify_hudi.sh`: hudi formatter, regex, index and nullness, then optionally hudi-utilities. 24 h limit. hudi-utilities is attempted last because it needs `packages.confluent.io`. hudi-metaserver-server needs Docker and is skipped.
- `submit_verify_ghidra.sh`: ghidra regex, resourceleak, interning, index and nullness. 72 h limit.

Each job checks its repos out under `/scratch/mjk76/ea442/fullproject-verify-work/`, not in the pipeline's `repos-pinned` checkouts, because the patches edit build files in place. A clone is reused if it is already at the pinned commit. Before each repo (light job) or each checker (hudi and ghidra jobs), `lib.sh` (`prepare_clone`) resets the clone to a clean tree at that commit. It prints any leftover changes it discards, for example a patch left behind by a killed job.

Logs go to `/project/mjk76/ea442/snippet-selection-pipeline-output/fullproject-verification/<repo>/`. At the end, each job prints the steps that exited non-zero. mybatis-3 exits 1 whenever its checker reports anything. That is expected, because its patches don't use `-Awarns`.
