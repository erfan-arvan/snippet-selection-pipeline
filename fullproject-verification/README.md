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
| netty | 11 (4 checkers x submodules) | Yes for index/interning/resourceleak; nullness partial (3/6 submodules) | 25 attempted, 6 unreached — `results_netty.csv` |
| dubbo | 12 (2 checkers x submodules) | Yes for index; nullness partial (3/6 modules) | 26 attempted, 4 unreached — `results_dubbo.csv` |
| ghidra | 5 (1 per checker) | Only regex + resourceleak confirmed; index/nullness/interning unrun | 2/114 — `ghidra/validated_results_partial.csv` |
| hudi | 4 (formatter, index, nullness, regex) | **Not validated at all** — treat first HPC run as the real first test | none |

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

Three SLURM scripts, split by how much is already proven:

- `submit_verify_light.sh` — apollo + mybatis-3 + netty + dubbo, ~12h.
- `submit_verify_hudi.sh` — hudi alone, unvalidated patches, ~24h. Two known blockers noted
  inline (Confluent deps behind a blocked host in the sandbox that built this — may work fine
  on HPC's network; Docker-dependent hudi-metaserver, skipped by default).
- `submit_verify_ghidra.sh` — ghidra alone, 72h timewall, needs Gradle >= 8.5 on PATH.

Each clones its own repo(s) **fresh** under `/scratch/mjk76/ea442/fullproject-verify-work/`
rather than reusing `/scratch/mjk76/ea442/repos-pinned/` — these scripts patch `pom.xml`/
`build.gradle` in place (reverted after each run, but still touching the file live), and this
avoids any chance of racing with the main pipeline if it's running at the same time. Results
land under `/project/mjk76/ea442/snippet-selection-pipeline-output/fullproject-verification/`.

All three assume a `mvn`/`gradle` module is loadable on HPC — neither was ever confirmed
working there specifically (only in the sandbox this was built in); check `module avail` if
the fallback `module load Maven/3.9.6` / `module load Gradle/8.9` lines don't resolve.
