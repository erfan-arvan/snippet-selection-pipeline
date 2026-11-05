# Dubbo full-project Checker Framework runs (for HPC)

Target: apache/dubbo @ `a5604cd2632471b46f66ed0217e84a68dc84a374`, Checker Framework 4.2.1.

## Files
- `run_checker.sh <clone> <index|nullness> <submodule[,submodule...]> [log]`: the main entry point. It installs dubbo-maven-plugin once if it's missing, patches the named submodule pom(s), runs `mvn -B -pl <mods> -am clean compile -Dspotless.skip -Dcheckstyle.skip -Drat.skip`, and reverts the poms when it exits.
- `patch_pom.py <clone> <checker> <submodule...>`: the pom patcher that `run_checker.sh` uses.
- `patches/<checker>__<submodule with / -> _>.diff`: the same edits as unified diffs against the pinned commit, one per (checker, submodule). Apply with `git apply`. Each was checked with `git apply --check` on a clean checkout.

The patch adds `checker-qual:4.2.1` and `checker:4.2.1` (the second as `provided`). It sets maven-compiler-plugin to `fork=true` and `maxmem=6g`, with `annotationProcessorPaths` pointing at `checker:4.2.1`. The compilerArgs are `-parameters -processor <X> -Awarns -Xmaxerrs 10000 -Xmaxwarns 10000`, plus `-J--add-opens=jdk.compiler/com.sun.tools.javac.{api,code,comp,file,main,model,parser,processing,tree,util,jvm}=ALL-UNNAMED`.

## Which submodule each target needs
| checker | submodule | target classes |
|---|---|---|
| index | dubbo-common | Bytes, ReflectUtils, UrlUtils, UnsafeByteArrayInputStream |
| nullness | dubbo-common | AbstractConfig, ClassGenerator, ReflectUtils, OperatingSystemBeanManager, JavaBeanSerializeUtil, ConfigConfigurationAdapter, ServiceAddressURL |
| nullness | dubbo-rpc/dubbo-rpc-api | MethodInvoker |
| nullness | dubbo-remoting/dubbo-remoting-netty | NettyServer |
| nullness | dubbo-rpc/dubbo-rpc-triple | SchemaDescriptorRegistry |
| nullness | dubbo-plugin/dubbo-qos | TelnetCommandDecoder |
| nullness | dubbo-metadata/dubbo-metadata-processor | TypeUtils |

## What was validated here and what wasn't
- **Index on dubbo-common: fully validated.** BUILD SUCCESS in 6m40s on 4 cores with 15 GB RAM. javac compiled 451 files and printed 630 checker warnings. All target index warnings reproduced.
- **Plain build (no checker) of all 6 modules with `-am`: validated.** BUILD SUCCESS, 54 reactor modules.
- **Nullness on all 6 modules: partly validated.** I stopped the run on request partway through reactor module 29/54 (dubbo-compiler). By then the Nullness compiles of **dubbo-common, dubbo-remoting-netty and dubbo-rpc-api had finished**, and their target warnings all reproduced. **The run never reached dubbo-rpc-triple, dubbo-qos or dubbo-metadata-processor** (modules 31 and later), so those 3 targets were not verified. Their patches are the same template and pass `git apply --check`, but they have not been run with a checker.
- The index patch was only run on dubbo-common, which is the only module with index targets. Index patches for the other modules are generated but were not run.

## Gotchas
1. **Reactor size.** Running `-pl` on the 6 target modules with `-am` builds 54 reactor modules: triple pulls in remoting-netty4, http12/http3, metrics, cluster, rpc-dubbo, the dubbo-compiler protoc plugin, and more. Only the patched poms run the checker. Everything else compiles normally (fast). To save time, run one target module per job, e.g. `run_checker.sh ./dubbo nullness dubbo-plugin/dubbo-qos`. Each job still builds that module's upstream chain without a checker.
2. **dubbo-maven-plugin: install it, and keep it out of the checker reactor.** dubbo-rpc-triple uses `dubbo-maven-plugin`, so `-am` pulls the plugin's own module into the reactor. Maven then loads the plugin from `dubbo-maven-plugin/target/classes`, which has no `META-INF/maven/plugin.xml` at the `compile` phase, and triple fails in under a second with `Failed to parse plugin descriptor ... No plugin descriptor found`. Installing the plugin alone does NOT fix this (that is what failed on Wulver). `run_checker.sh` installs the plugin first and then builds with `-pl <modules>,!dubbo-maven-plugin -am`, so the installed copy is used.
3. **Setting `JAVA_TOOL_OPTIONS` breaks dubbo-rpc-triple.** The child JVM's `Picked up JAVA_TOOL_OPTIONS` line goes to stderr, and dubbo-maven-plugin treats any protoc stderr as an error. It then silently skips adding the generated protobuf sources, and you get `package io.grpc.health.v1 does not exist`. `run_checker.sh` moves the value into `MAVEN_OPTS`. Many HPC module systems set `JAVA_TOOL_OPTIONS`, so watch for this.
4. **`-Awarns` is required.** It turns checker errors into `[WARNING] ...java:[l,c] [key] msg` lines. Without it, the first checker error fails dubbo-common and every module after it is skipped. Grep for `^\[WARNING\] /.*\.java:\[` to find the warnings.
5. **The build uses `--release 8`.** The parent pom's `jdk9-compile` profile sets it. JDK parameter names therefore show up as `arg0`/`arg1` in messages. For example, the full build prints `parameter arg0 of String.substring` where the slice-based scan printed `beginIndex`. Match on the key, not the parameter name.
6. **Expect some `[type.argument.inference.crashed]` warnings** under both checkers, for example in DubboAppender with Log4j `FileAppender.newBuilder`. They are internal checker issues on unrelated code and do not stop the build.
7. **Timing and memory.** On 4 cores, dubbo-common took about 6-7 min under Index and was similar under Nullness. Modules without a checker take seconds to tens of seconds each. Budget 6 GB heap for the forked javac (`maxmem`), and about 8 GB per job in total. Maven downloads dependencies the first time, so give jobs network access or pre-warm `~/.m2`.
8. **JDK and Maven versions.** Validated on OpenJDK 21.0.12 with Maven 3.9.11. The repo enforces its own Maven and Java version rules (enforcer plugin). JDK 17+ is needed for CF 4.2.1.
