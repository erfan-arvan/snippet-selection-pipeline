hudi full-project Checker Framework runner (CF 4.2.1)
=====================================================
Repo:   https://github.com/apache/hudi
Commit: cb32e5e1bac58cbccba8c92c91e7bed4780e9858 (2025-02-22, version 1.1.0-SNAPSHOT)

Files
-----
patches/hudi_formatter.patch  -> hudi-common/pom.xml
patches/hudi_regex.patch      -> hudi-common/pom.xml
patches/hudi_index.patch      -> hudi-io/pom.xml, hudi-common/pom.xml
patches/hudi_nullness.patch   -> hudi-io, hudi-common, hudi-hadoop-common,
                                 hudi-client/hudi-client-common, hudi-hadoop-mr,
                                 hudi-examples/hudi-examples-common, hudi-utilities,
                                 hudi-platform-service/hudi-metaserver/hudi-metaserver-server (pom.xml each)
run_hudi_checker.sh           applies a patch, runs the real reactor build, always reverts (trap EXIT)
patch_pom.py                  the generator used to produce the patches (for regenerating / other checkers:
                              python3 patch_pom.py <module>/pom.xml <processor class>)

Each patch only touches the module(s) that contain target classes from hudi.json. Upstream modules
pulled in by -am (hudi-tests-common, hudi-spark-*, hudi-aws, ...) compile WITHOUT the checker.

What the patch adds per module
  * deps org.checkerframework:checker-qual:4.2.1 (compile) and checker:4.2.1 (provided)
  * maven-compiler-plugin (existing 3.8.0 from parent; merged into the module's existing
    compiler <plugin> block where one exists, else a new block): fork=true, showWarnings=true,
    annotationProcessorPaths=checker:4.2.1, compilerArgs (combine.children="append"):
    -processor <class> -Xmaxerrs 10000 -Xmaxwarns 10000 -Awarns
    -J--add-opens=jdk.compiler/com.sun.tools.javac.{api,code,comp,file,main,model,parser,processing,tree,util,jvm}=ALL-UNNAMED

Usage
-----
  git init hudi && cd hudi && git remote add origin https://github.com/apache/hudi \
    && git fetch --depth 1 origin cb32e5e1bac58cbccba8c92c91e7bed4780e9858 && git checkout FETCH_HEAD
  # optional, only needed for hudi-utilities (nullness), needs network:
  ./run_hudi_checker.sh /path/to/hudi prep  /path/to/logs
  ./run_hudi_checker.sh /path/to/hudi formatter /path/to/logs
  ./run_hudi_checker.sh /path/to/hudi regex     /path/to/logs
  ./run_hudi_checker.sh /path/to/hudi index     /path/to/logs
  ./run_hudi_checker.sh /path/to/hudi nullness  /path/to/logs     # also writes build_nullness_metaserver.log
Diagnostics appear as lines like
  [WARNING] /.../hudi-common/src/main/java/.../Foo.java:[35,27] [group.count] invalid groups parameter ...
Match on file path (== qualified class) + bracketed key; then find the enclosing method by line number.

GOTCHAS (read before burning HPC hours)
---------------------------------------
1. -Awarns is deliberately added (beyond the original spec). Without it, CF diagnostics are javac
   ERRORS: the first patched module (e.g. hudi-io) fails, no .class files are written, and every
   downstream patched module is SKIPPED. With -Awarns they are [WARNING]s and the reactor continues.
   showWarnings=true is required too: maven-compiler-plugin 3.8.0 defaults to showWarnings=false
   (passes -nowarn), which would hide them.
2. Must use `clean compile`, not `compile`. If target/classes is up to date, compiler:3.8.0 says
   "Nothing to compile" and the checker never runs -> a false "no warnings" (=> false confirmed_artifact).
   Sanity check every log for "Compiling N source files" in each patched module.
3. -Denforcer.skip is required for compile-only reactor builds: maven-enforcer (enforce-logging) in
   hudi-common resolves test-scoped hudi-io:tests jar, which does not exist until `package`, and then
   tries apache.snapshots/confluent and fails ("Could not resolve ... hudi-io:jar:tests").
4. hudi-utilities (only BloomFilterData/nullness): its -am chain includes Scala modules
   (hudi-spark-common/hudi-spark3.5.x/hudi-spark), whose scala-maven-plugin resolves TEST scope,
   so it needs hudi-*:tests jars -> run `prep` (mvn install -DskipTests, no checker) once first.
   It ALSO needs io.confluent:kafka-avro-serializer etc. 5.5.0 from https://packages.confluent.io/maven/
   (not on Maven Central). In our sandbox that host was blocked by the egress proxy (403), so the
   hudi-utilities build could not resolve dependencies at all. On HPC, make sure that repo is
   reachable (or pre-seed ~/.m2 on a login node and use EXTRA_MVN_ARGS=-o on compute nodes).
   Use SKIP_UTILITIES=1 to run nullness on the other modules if confluent is unreachable.
5. hudi-metaserver-server (RelationalDBBasedStorage/nullness) is only in the reactor with
   -Phudi-platform-service, and its generate-sources step runs src/main/thrift/bin/thrift_in_docker.sh
   (`docker pull omnisci/thrift:0.13.0` + `docker run`). HPC nodes usually have no docker daemon.
   Alternative: install thrift 0.13.0 at /usr/local/bin/thrift and set METASERVER_LOCAL_THRIFT=1
   (activates hudi's own -Pthrift-gen-source profile). Or SKIP_METASERVER=1.
6. Runtime/memory: hudi-common is 648 source files and the forked javac+CF is single-threaded.
   In the sandbox (4 cores, 15 GB) the FormatterChecker pass over hudi-common alone had NOT finished
   after ~25 min at 100% of one core, ~1.7 GB RSS (it was stopped; no run was ever validated end to end). Nullness/Index will be slower and larger. Budget >=1-2 h per
   checker and >=8 GB RAM; the forked javac's default heap is 1/4 of node RAM - if your node is
   small, add <arg>-J-Xmx8g</arg> to compilerArgs. Do not run two checkers concurrently in the same
   clone (they share target/ dirs) - use one clone per checker if parallelising.
7. JDK: hudi documents Java 8/11/17; we built with JDK 21 (source/target=8, emits "source value 8 is
   obsolete" warnings - harmless). CF 4.x requires running javac on JDK 17+, so do not use JDK 8/11.
8. No source-rewriting plugins here (unlike mybatis-3's license/formatter plugin): hudi's spotless
   plugin is commented out; checkstyle (compile phase, failOnViolation) and apache-rat are check-only
   and are skipped anyway. Builds only write under target/ (incl. protobuf-generated sources in
   hudi-io/target and thrift sources in hudi-metaserver/target). `git status` stays clean after revert.
9. hudi-client-common, hudi-examples-common and hudi-utilities declare an extra compiler execution
   (id "default") at compile phase in addition to default-compile, so CF may run twice in those
   modules; the second run is usually "Nothing to compile". Dedupe diagnostics by file+line+key.
10. Network hosts touched: repo.maven.apache.org (fine), plus attempts to repository.apache.org/snapshots,
   packages.confluent.io, repository.cloudera.com, oss.sonatype.org (blocked/unresolvable in sandbox;
   harmless except for #4).
