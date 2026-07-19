package com.github.erfanarvan.methodanalyzerapp;

import com.github.javaparser.JavaParser;
import com.github.javaparser.ParserConfiguration;
import com.github.javaparser.symbolsolver.JavaSymbolSolver;
import com.github.javaparser.symbolsolver.resolution.typesolvers.CombinedTypeSolver;
import com.github.javaparser.symbolsolver.resolution.typesolvers.JarTypeSolver;
import com.github.javaparser.symbolsolver.resolution.typesolvers.JavaParserTypeSolver;
import com.github.javaparser.symbolsolver.resolution.typesolvers.ReflectionTypeSolver;

import java.io.File;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ExecutorService;

/**
 * Processes a single project directory: builds one symbol-resolution classpath for the whole
 * project (not per file - see {@link #buildClasspathSolver()}), then walks every non-test
 * .java file in it.
 * <p>
 * Classpath is discovered via two optional convention files placed at the project root by the
 * orchestrator's classpath-resolution stage (see the pipeline README):
 * <ul>
 *   <li>{@code .pipeline-classpath.txt} - one dependency jar path per line</li>
 *   <li>{@code .pipeline-sourceroot.txt} - one Java source root per line (e.g. multiple
 *       modules' {@code src/main/java}); if absent, falls back to auto-detecting
 *       {@code src/main/java} under the project root, or the project root itself</li>
 * </ul>
 * Without these files, resolution still works for JDK types via reflection, but project-owned
 * types and third-party dependencies will resolve as "Unresolved" - which criterion (1) then
 * conservatively treats as non-JDK. This means an under-specified classpath makes filtering
 * more conservative (fewer candidates pass), never less correct.
 */
public class ProjectProcessor {
    private final File projectDirectory;
    private final List<File> javaFiles;
    private final CSVWriter projectWriter;
    private final CSVWriter aggregatedWriter;
    private final ManifestWriter manifestWriter;
    private final ExecutorService executor;

    private static final String CLASSPATH_FILE = ".pipeline-classpath.txt";
    private static final String SOURCEROOT_FILE = ".pipeline-sourceroot.txt";

    public ProjectProcessor(
            File projectDirectory,
            CSVWriter aggregatedWriter,
            ManifestWriter manifestWriter,
            ExecutorService executor
    ) {
        this.projectDirectory = projectDirectory;
        this.javaFiles = new ArrayList<>();
        this.projectWriter = new CSVWriter(projectDirectory.getName() + "_methods.csv");
        this.aggregatedWriter = aggregatedWriter;
        this.manifestWriter = manifestWriter;
        this.executor = executor;
    }

    public void process() {
        // Built as an explicit JavaParser instance (not via the StaticJavaParser singleton):
        // StaticJavaParser's configuration is thread-local, so a resolver set on this
        // (calling) thread would be invisible to the shared executor's worker threads that
        // actually parse each file, causing every resolve() call downstream to fail with
        // "Symbol resolution not configured". An explicit instance carries its configuration
        // as ordinary object state, so it works no matter which thread does the parsing.
        JavaParser javaParser = new JavaParser(new ParserConfiguration().setSymbolResolver(buildClasspathSolver()));

        findJavaFiles(projectDirectory);
        String projectName = projectDirectory.getName();
        for (File javaFile : javaFiles) {
            String relativePath = projectDirectory.toPath().relativize(javaFile.toPath()).toString();
            JavaFileProcessor processor = new JavaFileProcessor(
                    javaFile,
                    relativePath,
                    projectName,
                    javaParser,
                    projectWriter,
                    aggregatedWriter,
                    manifestWriter,
                    executor
            );
            processor.process();
        }
        projectWriter.close();
    }

    private JavaSymbolSolver buildClasspathSolver() {
        CombinedTypeSolver combinedSolver = new CombinedTypeSolver();
        combinedSolver.add(new ReflectionTypeSolver());

        for (Path sourceRoot : discoverSourceRoots()) {
            combinedSolver.add(new JavaParserTypeSolver(sourceRoot.toFile()));
        }

        for (Path jar : discoverClasspathJars()) {
            try {
                combinedSolver.add(new JarTypeSolver(jar.toFile()));
            } catch (IOException e) {
                System.err.println("Skipping unreadable classpath jar " + jar + ": " + e.getMessage());
            }
        }

        return new JavaSymbolSolver(combinedSolver);
    }

    private List<Path> discoverSourceRoots() {
        List<Path> roots = new ArrayList<>();
        Path sourceRootFile = projectDirectory.toPath().resolve(SOURCEROOT_FILE);
        if (Files.isRegularFile(sourceRootFile)) {
            try {
                for (String line : Files.readAllLines(sourceRootFile)) {
                    String trimmed = line.trim();
                    if (trimmed.isEmpty() || trimmed.startsWith("#")) continue;
                    Path resolved = Paths.get(trimmed);
                    roots.add(resolved.isAbsolute() ? resolved : projectDirectory.toPath().resolve(resolved));
                }
            } catch (IOException e) {
                System.err.println("Failed to read " + sourceRootFile + ": " + e.getMessage());
            }
        }
        if (roots.isEmpty()) {
            Path conventional = projectDirectory.toPath().resolve("src/main/java");
            roots.add(Files.isDirectory(conventional) ? conventional : projectDirectory.toPath());
        }
        return roots;
    }

    private List<Path> discoverClasspathJars() {
        List<Path> jars = new ArrayList<>();
        Path classpathFile = projectDirectory.toPath().resolve(CLASSPATH_FILE);
        if (Files.isRegularFile(classpathFile)) {
            try {
                for (String line : Files.readAllLines(classpathFile)) {
                    String trimmed = line.trim();
                    if (trimmed.isEmpty() || trimmed.startsWith("#")) continue;
                    Path resolved = Paths.get(trimmed);
                    jars.add(resolved.isAbsolute() ? resolved : projectDirectory.toPath().resolve(resolved));
                }
            } catch (IOException e) {
                System.err.println("Failed to read " + classpathFile + ": " + e.getMessage());
            }
        }
        return jars;
    }

    private void findJavaFiles(File directory) {
        File[] files = directory.listFiles();
        if (files == null) return;

        for (File file : files) {
            if (file.isDirectory()) {
                findJavaFiles(file);
            } else if (file.getName().endsWith(".java")) {
                if (!isTestFile(file)) {
                    javaFiles.add(file);
                }
            }
        }
    }

    /** A file is considered a test file if any path segment relative to the project root is "test" or "tests". */
    private boolean isTestFile(File file) {
        Path relative = projectDirectory.toPath().relativize(file.toPath());
        for (Path segment : relative) {
            String name = segment.toString().toLowerCase();
            if (name.equals("test") || name.equals("tests")) {
                return true;
            }
        }
        return false;
    }
}
