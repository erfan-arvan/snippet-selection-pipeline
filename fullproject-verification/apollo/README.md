# Apollo full-project NullnessChecker run

Files:
- `apollo-nullness-pom.patch`: unified diff against the root `pom.xml` at commit `5eb320f7fdf0c183904e9aff501392c878fec62f`.
- `pom.xml.patched`: the same root pom with the patch already applied.
- `run_nullness.sh <apollo-clone> [log]`: applies the patch, runs `mvn -B -pl apollo-portal -am clean compile -DskipTests`, then restores `pom.xml`.

Get the clone:

    git init apollo && cd apollo
    git remote add origin https://github.com/apolloconfig/apollo
    git fetch --depth 1 origin 5eb320f7fdf0c183904e9aff501392c878fec62f
    git checkout 5eb320f7fdf0c183904e9aff501392c878fec62f

What the patch adds:
- `checker-qual` and `checker` 4.2.1 as dependencies in the root `<dependencies>`.
- In the root `pluginManagement` maven-compiler-plugin config, which every module inherits:
  - `<fork>true</fork>`
  - `annotationProcessorPaths` pointing at `checker` 4.2.1
  - `-processor org.checkerframework.checker.nullness.NullnessChecker -Awarns -Xmaxerrs 10000 -Xmaxwarns 10000`
  - `-J--add-opens=jdk.compiler/com.sun.tools.javac.{api,code,comp,file,main,model,parser,processing,tree,util,jvm}=ALL-UNNAMED`

Gotchas:
1. **You need `-Awarns`.** Without it, checker errors in the upstream modules (apollo-common, apollo-audit-*) stop the reactor before apollo-portal compiles. With it, the same diagnostics come out as `[WARNING]`s and the build finishes.
2. **`-Awarns` is a javac option, not a Maven option.** It lives in the pom's `<compilerArgs>`. `mvn ... -Awarns` on the command line does not work.
3. **You need JDK 17+ and the `--add-opens` flags.** Without the flags the checker crashes with IllegalAccessError. Tested on OpenJDK 21.0.12 with Maven 3.9.11.
4. **The pom keeps `source`/`target` 1.8.** javac 21 accepts this and only prints obsolete-option warnings, which you can ignore.
5. **Only the checker runs.** Using `annotationProcessorPaths` with an explicit `-processor` means apollo-portal's `spring-boot-configuration-processor` does not run. That processor only generates metadata and doesn't affect the analysis.
6. **Always build with `clean`.** If the classes are already compiled, Maven prints "Nothing to compile - all classes are up to date" and the checker never runs. You get BUILD SUCCESS with 0 warnings, which looks like a clean result but is not one. The script runs `clean compile`.
7. **Network access.** The first run downloads dependencies from Maven Central. On compute nodes without network, warm `~/.m2` first, for example with `mvn dependency:go-offline` on a login node, then pass `-o`.

Expected result (reference run): BUILD SUCCESS on 8 modules. 560 checker warnings in total, 355 of them in apollo-portal. Among them:
- `RoleUtils.java:[62,62] [argument] ... parameter env of RoleUtils.buildModifyNamespaceRoleName`
- `SpringSecurityUserService.java:[147,26] [return] incompatible types in return.`
