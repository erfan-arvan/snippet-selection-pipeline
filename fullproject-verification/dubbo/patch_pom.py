"""Patch one or more dubbo submodule pom.xml files to run a Checker Framework checker.

Usage: python3 -I patch_pom.py <dubbo_repo_dir> <index|nullness> <submodule> [<submodule> ...]
  e.g. python3 -I patch_pom.py ./dubbo nullness dubbo-common dubbo-rpc/dubbo-rpc-api

Written against apache/dubbo commit a5604cd2632471b46f66ed0217e84a68dc84a374.
Edits are idempotent-guarded (refuses to patch a pom twice).
"""
import sys, pathlib

PROCESSORS = {
    "index": "org.checkerframework.checker.index.IndexChecker",
    "nullness": "org.checkerframework.checker.nullness.NullnessChecker",
}
CF_VERSION = "4.2.1"
OPEN_PKGS = ["api", "code", "comp", "file", "main", "model", "parser",
             "processing", "tree", "util", "jvm"]

repo = pathlib.Path(sys.argv[1])
checker = sys.argv[2]
modules = sys.argv[3:]
if checker not in PROCESSORS or not modules:
    sys.exit(__doc__)
processor = PROCESSORS[checker]

deps = f"""
    <!-- checker-framework-reaudit: BEGIN deps -->
    <dependency>
      <groupId>org.checkerframework</groupId>
      <artifactId>checker-qual</artifactId>
      <version>{CF_VERSION}</version>
    </dependency>
    <dependency>
      <groupId>org.checkerframework</groupId>
      <artifactId>checker</artifactId>
      <version>{CF_VERSION}</version>
      <scope>provided</scope>
    </dependency>
    <!-- checker-framework-reaudit: END deps -->
"""

opens = "\n".join(
    f"            <compilerArg>-J--add-opens=jdk.compiler/com.sun.tools.javac.{p}=ALL-UNNAMED</compilerArg>"
    for p in OPEN_PKGS)

# Notes on the compilerArgs:
#  * The parent pom sets <compilerArgs>-proc:none -parameters</compilerArgs>. A child <compilerArgs>
#    REPLACES the parent list (no combine.children), which is what drops -proc:none. -parameters is
#    re-added to stay faithful to the real build.
#  * -Awarns turns checker errors into warnings. Without it the first checker error fails the
#    module and every downstream module in the reactor is skipped.
plugin = f"""
      <!-- checker-framework-reaudit: BEGIN plugin -->
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-compiler-plugin</artifactId>
        <configuration>
          <fork>true</fork>
          <meminitial>1024m</meminitial>
          <maxmem>6g</maxmem>
          <annotationProcessorPaths>
            <path>
              <groupId>org.checkerframework</groupId>
              <artifactId>checker</artifactId>
              <version>{CF_VERSION}</version>
            </path>
          </annotationProcessorPaths>
          <compilerArgs>
            <compilerArg>-parameters</compilerArg>
            <compilerArg>-processor</compilerArg>
            <compilerArg>{processor}</compilerArg>
            <compilerArg>-Awarns</compilerArg>
            <compilerArg>-Xmaxerrs</compilerArg>
            <compilerArg>10000</compilerArg>
            <compilerArg>-Xmaxwarns</compilerArg>
            <compilerArg>10000</compilerArg>
{opens}
          </compilerArgs>
        </configuration>
      </plugin>
      <!-- checker-framework-reaudit: END plugin -->
"""

for m in modules:
    p = repo / m / "pom.xml"
    s = p.read_text()
    if "checker-framework-reaudit" in s:
        sys.exit(f"{p} is already patched; run `git checkout -- {m}/pom.xml` first")
    if s.count("<dependencies>") != 1:
        sys.exit(f"{p}: expected exactly one <dependencies> block, found {s.count('<dependencies>')}")
    s = s.replace("<dependencies>", "<dependencies>" + deps, 1)
    if "<build>" in s:
        if s.count("<build>") != 1:
            sys.exit(f"{p}: multiple <build> blocks, refusing to guess")
        idx = s.index("<build>")
        pidx = s.index("<plugins>", idx) + len("<plugins>")
        s = s[:pidx] + plugin + s[pidx:]
    else:
        s = s.replace("</project>",
                      "  <build>\n    <plugins>" + plugin + "    </plugins>\n  </build>\n</project>")
    p.write_text(s)
    print(f"patched {p} for {checker} ({processor})")
