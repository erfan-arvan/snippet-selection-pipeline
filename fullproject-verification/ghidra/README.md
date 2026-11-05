# Ghidra full-project Checker Framework re-audit: HPC kit

Pinned commit: `93c19e3cc6733fab119ace63a39be2aec89208b3` (Ghidra 11.4-DEV, Feb 2025).
Requirements: JDK >= 21 (`application.java.min=21`), Gradle >= 8.5 (validated with 8.14.3, JDK 21.0.12), python3, curl, git.

## Contents

| file | what |
|---|---|
| `run_ghidra_checker.sh` | init + patch + module-scoped build + revert, for one checker |
| `patches/<checker>.patch` | unified diff (apply with `git apply` at the clone root) adding CF to the target modules' `build.gradle` |
| `patches/<checker>.tasks` | the exact Gradle tasks to run for that checker |
| `match_targets.py` + `Locator.java` | maps build warnings to class+method (javac tree API) and writes the results CSV |
| `ghidra_manifest.json` | copy of the target manifest (114 diagnostics) |
| `validated_results_partial.csv` | the 2 targets actually verified here (regex, resourceleak) |
| `logs/` | full build logs for the two validated runs |

## Usage

```bash
# clone at the pinned commit
git init ghidra && cd ghidra
git remote add origin https://github.com/NationalSecurityAgency/ghidra
git fetch --depth 1 origin 93c19e3cc6733fab119ace63a39be2aec89208b3 && git checkout FETCH_HEAD && cd ..

# (login node, needs network) one-time init + warm the Gradle cache
./run_ghidra_checker.sh --init-only ghidra
./run_ghidra_checker.sh ghidra regex          # small; also warms Maven deps for BSim

# per checker (compute node; add GRADLE_OFFLINE=1 if the node has no network)
./run_ghidra_checker.sh ghidra nullness logs/nullness.log
python3 -I match_targets.py ghidra_manifest.json ghidra nullness logs/nullness.log --csv results_ghidra.csv --append
```
On the first `match_targets.py` call, leave out `--append` so the CSV header gets written. The runner refuses to patch a clone that has modified tracked files, and it reverts the patched `build.gradle` files when it exits, even if the build fails.

## Modules per checker (Gradle project names are the directory leaf names, e.g. `:Base`, not `:Ghidra:Features:Base`)

- **index** (49 targets): ProposedUtils BSim Base FileFormats FunctionGraph Recognizers DB Docking Generic Project SoftwareModeling
- **interning** (14): ProposedUtils Base
- **nullness** (49): DMG(`:DMG:compileDmgJava`) ProposedUtils BSim Base BytePatterns ByteViewer Decompiler FunctionID GraphServices Recognizers SourceCodeLookup VersionTracking Docking Generic Graph Help Project SoftwareModeling Utility
- **regex** (1): BSim
- **resourceleak** (1): Debugger-isf

## Gotchas (all hit in practice)

1. **flatRepo / "Unable to find the local maven repo"**: you must first run ghidra's documented init, `gradle -I gradle/support/fetchDependencies.gradle` (DevGuide.md, "Common Gradle Tasks"). It creates `dependencies/flatRepo/{java-sarif-2.1-modified.jar,AXMLPrinter2.jar}`, which modules resolve via flatDir. `prepdev`, natives and sleigh are NOT needed for `compileJava`.
2. **fetchDependencies fails behind restrictive proxies**: the script downloads from `https://github.com/NationalSecurityAgency/ghidra-data/raw/Ghidra_11.4/...`. Here that URL got HTTP 403 while `raw.githubusercontent.com/.../Ghidra_11.4/...` worked. The script then dies with the misleading `Cannot invoke method getAt() on null object` (line 409). `ftp.postgresql.org` and `archive.eclipse.org` were blocked outright. The runner's fallback pre-downloads into `dependencies/downloads/` with curl, rewriting the github URL (the script skips any file whose sha256 already matches). If anything is still missing, it writes an untracked `gradle/support/fetchDependencies_local.gradle` without those entries. That file must sit in `gradle/support/` because the script derives REPO_DIR from its own path. Only postgresql (source for BSim's native PG extension) and Eclipse CDT (GhidraDev plugin) were dropped, and neither is a Java compile input.
3. **GRADLE_USER_HOME**: the runner keeps an existing value (your HPC setup). It only defaults to `<clone>/../ghidra_gradle_user_home` when unset. The cold cache is about 1-2 GB.
4. **Maven Central HTTP 429**: on a cold cache, Gradle got `Received status code 429 ... Too Many Requests` (junit 4.12, protoc 3.21.8). This is transient. The runner retries up to 3x with a 60 s wait, and `--continue` keeps other modules going.
5. **`options.warnings = false` in ghidra's `gradle/javaProject.gradle`** (equivalent to `-nowarn`). The patch sets `options.warnings = true` and passes `-Awarns`. Without `-Awarns`, checker errors (nullness/index default to errors) fail an upstream module (e.g. Generic), and every dependent target module (Base, ...) then never compiles. With `-Awarns`, everything is reported as `warning: [key]` and the build continues. This changes severity only, not which diagnostics are issued.
6. **`--add-opens`** for the jdk.compiler packages api, code, comp, file, main, model, parser, processing, tree, util, jvm go in `forkOptions.jvmArgs`. Ghidra already forks javac (`options.fork = true`). Fork heap is set to `7g` for Base (3.3k files) and SoftwareModeling (1.6k). Request >= 12-16 GB per job, since Gradle itself takes 2 GB (`org.gradle.jvmargs=-Xmx2G`).
7. **Groovy, not Kotlin build files.** The `plugins { id 'org.checkerframework' version '0.6.42' }` block is prepended as line 1, because `plugins{}` must precede `apply from:`. Note that `Ghidra/Framework/Generic/build.gradle` already contains `exclude group: 'org.checkerframework', module: 'checker-qual'` (from guava). That is harmless, but don't grep for "org.checkerframework" to decide whether a file is patched.
8. **GPL/DMG** uses a custom `dmg` source set: its sources are in `src/dmg/java` and the task is `:DMG:compileDmgJava`. Plain `:DMG:compileJava` compiles nothing.
9. **UP-TO-DATE = silent**: a compile task that Gradle considers UP-TO-DATE prints no diagnostics, which would read as "no warning" and give a false `confirmed_artifact`. The runner passes `--rerun` after every target task (Gradle >= 7.6). `match_targets.py` also marks targets `could_not_verify` if the module's task did not execute or FAILED.
10. Debugger-isf runs `generateProto` (downloads `protoc` from Maven Central), so it needs network or a warm cache.
11. Diagnostic format: `<abs path>.java:<line>: warning: [<key>] <message>`. The slices used stub parameter names (`arg0`, `parameter1`); the full build uses real names, so match on key + class + method, not on the message text. Resource-leak messages in CF 4.2.1 here print literally as `[required.method.not.called]`.
12. Several manifest entries are repeated (same snippet_id, key and message, i.e. multiple occurrences). The matcher treats them as a multiset. Rows marked "fewer occurrences ... REVIEW" need a manual look.

## Validation status (this environment)

- **Validated end-to-end**:
  - regex on `:BSim`: the target persists (NotMd5BSimFilterType.java:65).
  - resourceleak on `:Debugger-isf`: the target persists (IsfClientHandler.java:117).
  - The regex run was repeated through `run_ghidra_checker.sh` itself, including the forced init fallback.
  - A baseline compile of all 23 target modules without CF succeeded.
- **Started, not completed**: interning on `:Base`/`:ProposedUtils`. CF ran and emitted `not.interned` warnings in Base (e.g. ByteCopier.java:288) before the run was stopped at the change of scope. No results were recorded.
- **Not run**: index and nullness. Their patches were generated by the same injector, but they have not been built here.
