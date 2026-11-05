# mybatis-3 full-project Checker Framework runs

Target: https://github.com/mybatis/mybatis-3 at commit `ed5512752c2a744202574345631b59a6b0d0ba1e`, Checker Framework 4.2.1.

## Files
- `pom_interning.patch`, `pom_nullness.patch`: unified diffs against the pinned commit's `pom.xml`. They are applied with `git apply`.
- `pom_interning.xml`, `pom_nullness.xml`: the same patched `pom.xml` files in full, if you would rather copy them over the original.
- `run_checker.sh`: applies a patch, builds, saves the log, and restores `pom.xml`.

Each patch adds `checker-qual` and `checker` (both 4.2.1) as dependencies. In `maven-compiler-plugin` it adds `checker` to `<annotationProcessorPaths>`, alongside the existing byte-buddy-agent entry. It also sets `<fork>true</fork>` and adds these compiler args:
- `-processor <checker>`
- `-Xmaxerrs 10000` and `-Xmaxwarns 10000`
- `-J--add-opens=jdk.compiler/com.sun.tools.javac.{api,code,comp,file,main,model,parser,processing,tree,util,jvm}=ALL-UNNAMED`

## Usage
```
git init mybatis-3 && cd mybatis-3
git remote add origin https://github.com/mybatis/mybatis-3
git fetch --depth 1 origin ed5512752c2a744202574345631b59a6b0d0ba1e
git checkout ed5512752c2a744202574345631b59a6b0d0ba1e
cd ..
./run_checker.sh interning ./mybatis-3
./run_checker.sh nullness  ./mybatis-3
```
Requirements: JDK 17 or 21 (I tested on 21.0.12) and Maven >= 3.9.9. The script exits with mvn exit=1 and "COMPILATION ERROR" whenever the checker reports anything. That is expected, because the checker reports its diagnostics as errors. On my run there were 146 unique interning diagnostics and 975 unique nullness diagnostics.

## IMPORTANT: skip flags for repos using the mybatis parent POM
`org.mybatis:mybatis-parent` (version 48 here) binds whitespace:trim, formatter:format, impsort:sort and license:format to phases that run before `compile`. All four rewrite source files in place. A plain `mvn compile` therefore analyzes modified source, not the pinned commit. For example, the license plugin bumps the copyright year in every file, and the formatter or import sorter can shift line numbers.

**Any other repo that inherits `mybatis-parent` will need the same flags.** This includes mybatis-spring, mybatis-dynamic-sql, the mybatis generator and migrations projects, spring-boot-starter, and others:
```
-Dlicense.skip=true -Dformatter.skip=true -Dimpsort.skip=true -Dwhitespace.skip=true
```
After each build, check that `git status` shows no changes other than `pom.xml`. `run_checker.sh` does this check and prints a warning if anything else changed.
