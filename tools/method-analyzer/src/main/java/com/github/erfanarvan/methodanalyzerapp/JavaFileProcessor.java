package com.github.erfanarvan.methodanalyzerapp;

import com.github.javaparser.JavaParser;
import com.github.javaparser.ParseResult;
import com.github.javaparser.ast.CompilationUnit;

import java.io.File;
import java.io.FileNotFoundException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

/**
 * Parses a single Java source file and delegates method-level extraction to
 * {@link MethodExtractor}. The symbol solver is configured once per project by
 * {@link ProjectProcessor} (not per file) so that type resolution sees the project's full
 * classpath rather than just the file's own directory; it's carried on an explicit
 * {@link JavaParser} instance rather than the {@code StaticJavaParser} singleton, since that
 * singleton's configuration is thread-local and this file may be parsed on a different
 * executor worker thread than the one that configured the resolver.
 */
public class JavaFileProcessor {
    private final File javaFile;
    private final String relativePath;
    private final String projectName;
    private final JavaParser javaParser;
    private final CSVWriter projectWriter;
    private final CSVWriter aggregatedWriter;
    private final ManifestWriter manifestWriter;
    private final ExecutorService executor;
    private static final int PARSE_TIMEOUT_MS = 5000;

    public JavaFileProcessor(
            File javaFile,
            String relativePath,
            String projectName,
            JavaParser javaParser,
            CSVWriter projectWriter,
            CSVWriter aggregatedWriter,
            ManifestWriter manifestWriter,
            ExecutorService executor
    ) {
        this.javaFile = javaFile;
        this.relativePath = relativePath;
        this.projectName = projectName;
        this.javaParser = javaParser;
        this.projectWriter = projectWriter;
        this.aggregatedWriter = aggregatedWriter;
        this.manifestWriter = manifestWriter;
        this.executor = executor;
    }

    public void process() {
        Future<CompilationUnit> future = executor.submit(this::parse);

        try {
            CompilationUnit cu = future.get(PARSE_TIMEOUT_MS, TimeUnit.MILLISECONDS);
            if (cu != null) {
                MethodExtractor extractor = new MethodExtractor(
                        javaFile,
                        relativePath,
                        projectName,
                        cu,
                        projectWriter,
                        aggregatedWriter,
                        manifestWriter,
                        executor
                );
                extractor.extract();
            }
        } catch (TimeoutException e) {
            future.cancel(true);
            System.err.println("Timeout parsing file: " + javaFile.getName());
        } catch (Exception e) {
            System.err.println("Error parsing file: " + javaFile.getName() + " - " + e.getMessage());
        }
    }

    private CompilationUnit parse() throws FileNotFoundException {
        ParseResult<CompilationUnit> result = javaParser.parse(javaFile);
        if (!result.isSuccessful() || result.getResult().isEmpty()) {
            System.err.println("Failed to parse " + javaFile + ": " + result.getProblems());
            return null;
        }
        return result.getResult().get();
    }
}
