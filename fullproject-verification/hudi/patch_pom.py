#!/usr/bin/env python3
"""Inject Checker Framework 4.2.1 config into a real module pom.xml.
usage: patch_pom.py <pom.xml> <processor_class>
"""
import re, sys

pom_path, processor = sys.argv[1], sys.argv[2]
src = open(pom_path).read()
CF = "4.2.1"
pkgs = ["api", "code", "comp", "file", "main", "model", "parser", "processing", "tree", "util", "jvm"]
opens = "\n".join(
    f"            <arg>-J--add-opens=jdk.compiler/com.sun.tools.javac.{p}=ALL-UNNAMED</arg>" for p in pkgs)
cfg_inner = f"""
          <fork>true</fork>
          <showWarnings>true</showWarnings>
          <annotationProcessorPaths>
            <path>
              <groupId>org.checkerframework</groupId>
              <artifactId>checker</artifactId>
              <version>{CF}</version>
            </path>
          </annotationProcessorPaths>
          <compilerArgs combine.children="append">
            <arg>-processor</arg>
            <arg>{processor}</arg>
            <arg>-Xmaxerrs</arg>
            <arg>10000</arg>
            <arg>-Xmaxwarns</arg>
            <arg>10000</arg>
            <arg>-Awarns</arg>
{opens}
          </compilerArgs>
"""
deps = f"""
    <dependency>
      <groupId>org.checkerframework</groupId>
      <artifactId>checker-qual</artifactId>
      <version>{CF}</version>
    </dependency>
    <dependency>
      <groupId>org.checkerframework</groupId>
      <artifactId>checker</artifactId>
      <version>{CF}</version>
      <scope>provided</scope>
    </dependency>
"""

# --- locate the top-level <build><plugins> (not inside <profiles>) ---
prof = src.find("<profiles>")
def top(idx):
    if idx == -1:
        return False
    ps = src.find("<profiles>"); pe = src.find("</profiles>")
    return ps == -1 or idx < ps or idx > pe

# dependencies: first top-level <dependencies> not inside dependencyManagement
m = None
for mm in re.finditer(r"<dependencies>", src):
    before = src[:mm.start()]
    if before.count("<dependencyManagement>") > before.count("</dependencyManagement>"):
        continue
    if not top(mm.start()):
        continue
    m = mm
    break
assert m, "no top-level <dependencies>"
src = src[:m.end()] + deps + src[m.end():]

# find top-level build/plugins
b = src.find("<build>")
while b != -1 and not top(b):
    b = src.find("<build>", b + 1)
assert top(b), "no top-level <build>"
pm = src.find("<pluginManagement>", b)
pl = src.find("<plugins>", b)
assert top(pl)
if pm != -1 and pm < pl:
    pl = src.find("<plugins>", src.find("</pluginManagement>", b))
assert top(pl)
plend = src.find("</plugins>", pl)
section = src[pl:plend]
cm = re.search(r"<artifactId>maven-compiler-plugin</artifactId>", section)
if cm:
    # existing plugin: find its <plugin> bounds
    abs_a = pl + cm.start()
    p_end = src.find("</plugin>", abs_a)
    plugin_txt = src[abs_a:p_end]
    # top-level configuration of this plugin (not inside executions)
    ex = plugin_txt.find("<executions>")
    cf = plugin_txt.find("<configuration>")
    if cf != -1 and (ex == -1 or cf < ex):
        ins = abs_a + cf + len("<configuration>")
        src = src[:ins] + cfg_inner + src[ins:]
    elif cf != -1 and ex != -1 and cf > plugin_txt.find("</executions>"):
        ins = abs_a + cf + len("<configuration>")
        src = src[:ins] + cfg_inner + src[ins:]
    else:
        ins = abs_a + len("<artifactId>maven-compiler-plugin</artifactId>")
        src = src[:ins] + "\n        <configuration>" + cfg_inner + "        </configuration>" + src[ins:]
else:
    ins = pl + len("<plugins>")
    block = ("\n      <plugin>\n        <groupId>org.apache.maven.plugins</groupId>\n"
             "        <artifactId>maven-compiler-plugin</artifactId>\n        <configuration>"
             + cfg_inner + "        </configuration>\n      </plugin>")
    src = src[:ins] + block + src[ins:]
open(pom_path, "w").write(src)
print("patched", pom_path)
