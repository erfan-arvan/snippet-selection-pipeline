package com.github.erfanarvan.methodanalyzerapp;

import java.io.File;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class DirectoryProcessor {
    private final File rootDirectory;
    private final List<File> projects;
    private final CSVWriter aggregatedWriter;
    private final ManifestWriter manifestWriter;
    private final ExecutorService executor;
    private static final String AGGREGATED_CSV = "aggregated_methods.csv";

    /**
     * Initializes a `DirectoryProcessor` to analyze multiple Java projects within a root directory.
     * Each immediate subdirectory of {@code rootPath} is treated as one project (this is how the
     * orchestrator lays out the 16 target repos: as sibling directories under one root).
     *
     * @param rootPath     The path to the root directory containing multiple Java projects.
     * @param manifestPath Where to write the JSON Lines manifest (the canonical, non-lossy output).
     */
    public DirectoryProcessor(String rootPath, String manifestPath) {
        this.rootDirectory = new File(rootPath);
        this.projects = new ArrayList<>();

        File aggregatedFile = new File(AGGREGATED_CSV);
        if (aggregatedFile.exists() && !aggregatedFile.delete()) {
            System.err.println("Failed to delete aggregated CSV file.");
        }
        this.aggregatedWriter = new CSVWriter(AGGREGATED_CSV);
        this.manifestWriter = new ManifestWriter(manifestPath);

        // Shared across the whole run so per-expression type resolution doesn't pay
        // thread-creation cost on every call; sized generously since most tasks finish
        // in well under a millisecond and only pathological cases hit the timeout.
        int threads = Math.max(4, Runtime.getRuntime().availableProcessors() * 2);
        this.executor = Executors.newFixedThreadPool(threads);
    }

    public void processProjects() {
        findProjects(rootDirectory);
        for (File project : projects) {
            System.out.println("Processing project: " + project.getName());
            ProjectProcessor projectProcessor = new ProjectProcessor(project, aggregatedWriter, manifestWriter, executor);
            projectProcessor.process();
        }
        aggregatedWriter.close();
        manifestWriter.close();
        executor.shutdown();
        System.out.println("Processing completed.");
    }

    private void findProjects(File directory) {
        if (directory.isDirectory()) {
            File[] files = directory.listFiles();
            if (files == null) return;
            for (File file : files) {
                if (file.isDirectory()) {
                    projects.add(file);
                }
            }
        }
    }
}
