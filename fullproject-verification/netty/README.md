# netty full-project Checker Framework runs (commit f0a546dffa0d8644eb6c1f23433601cf464c0882)

## Setup
```
git init netty && cd netty && git remote add origin https://github.com/netty/netty
git fetch --depth 1 origin f0a546dffa0d8644eb6c1f23433601cf464c0882 && git checkout f0a546dffa0d8644eb6c1f23433601cf464c0882
../hpc_scripts_netty/run_checker.sh . nullness codec-http,codec-http2,resolver-dns
```
Tested with JDK 21.0.12 and Maven 3.9.11. Checker Framework 4.2.1 comes from Maven Central.

## Files
- `patches/<checker>__<submodule>.patch`: unified diff against the pinned `<submodule>/pom.xml`. Each adds `checker-qual` and `checker` 4.2.1 as dependencies, plus a `maven-compiler-plugin` `default-compile` execution with: `annotationProcessorPaths` (checker 4.2.1), `-processor <class>`, `-Awarns`, `-Xmaxerrs 10000`, `-Xmaxwarns 10000`, `fork=true`, `maxmem=6g`, and `-J--add-opens=jdk.compiler/com.sun.tools.javac.{api,code,comp,file,main,model,parser,processing,tree,util,jvm}=ALL-UNNAMED`.
- `patch_pom.py <pom> <processor_class>`: generates the same patch for any other submodule.
- `run_checker.sh <clone> <checker> <mods> [goal]`: applies the patch(es), runs `mvn -pl <mods> -am clean <goal>`, writes `<clone>/cf_<checker>.log`, and then reverts the poms.

## What was validated here
| checker | submodules | status |
|---|---|---|
| interning | common | full run, BUILD SUCCESS (~1 min) |
| resourceleak | transport | full run, BUILD SUCCESS (~2.5 min; transport alone takes ~1.5 min) |
| index | common, resolver-dns, codec-http | full run, BUILD SUCCESS (~9 min; common ~3.5 min, codec-http ~3 min) |
| nullness | common, transport-native-unix-common, handler | main-source compile of all three finished and produced warnings. The run was then stopped during handler test-compile, so this is not a complete BUILD SUCCESS |
| nullness | codec-http, codec-http2, resolver-dns | NOT run (stopped when the scope changed). The patches are from the same template, but no build used them |

## Gotchas
- **Use `test-compile`, not `compile`.** `mvn -pl <x> -am compile` fails whenever the `-am` set includes `codec`. netty-codec has a test-scoped `netty-transport:jar:tests` dependency, which the reactor cannot resolve at the `compile` phase. Maven then tries oss.sonatype.org for a SNAPSHOT and fails. `test-compile` makes `transport/target/test-classes` available. The checker is attached only to `default-compile` (main sources), so test code is compiled normally and not checked.
- **`-Awarns` is needed.** Without it, checker diagnostics are errors, and the first checked module fails and stops the reactor.
- **Indentation matters.** netty's build validates pom.xml formatting, and a mis-indented element causes BUILD FAILURE in the root `Netty` module ("Insert 2 spaces. Expected 16 found 14..."). Keep the patch formatting exactly as it is.
- **Run `clean`.** maven-compiler-plugin 3.8.0 does not recompile when only the pom changes. Without `clean`, stale classes mean no checker runs.
- **Memory.** netty's default `maxmem` is 1024m, which is too small for the checkers. The patches set 6g.
- Run checkers one at a time in a given clone, because every run rewrites the poms. On HPC, use one clone per concurrent job.
- `-Dcheckstyle.skip -Danimal.sniffer.skip` only skip lint plugins. They do not change compilation.
- The build with `-am` also compiles unpatched upstream modules (buffer, resolver, codec, codec-dns, ...) without the checker. That is expected: their classes are on the classpath as in a normal build.
- Submodule directory names are the ones `-pl` takes: `common`, `transport`, `handler`, `codec-http`, `codec-http2`, `resolver-dns`, `transport-native-unix-common`.
