package com.github.erfanarvan.methodanalyzerapp;

import com.google.gson.Gson;
import com.google.gson.GsonBuilder;

import java.io.File;
import java.io.IOException;
import java.io.PrintWriter;

/**
 * Writes one JSON object per line (JSON Lines) describing a single candidate method.
 * <p>
 * This is the canonical machine-readable output consumed by the Python orchestrator
 * downstream. Unlike the CSV output, JSON fields are never lossily sanitized (commas,
 * quotes, and newlines in parameter-type lists or Javadoc text are preserved exactly),
 * which matters because the orchestrator needs an exact parameter-type list to build
 * Specimin's {@code --targetMethod} signature string.
 * </p>
 */
public class ManifestWriter implements AutoCloseable {

    private final PrintWriter writer;
    private final Gson gson = new GsonBuilder().disableHtmlEscaping().create();

    public ManifestWriter(String outputPath) {
        File outputFile = new File(outputPath);
        File parent = outputFile.getParentFile();
        if (parent != null && !parent.exists() && !parent.mkdirs()) {
            throw new RuntimeException("Failed to create manifest output directory: " + parent);
        }
        try {
            this.writer = new PrintWriter(outputFile, "UTF-8");
        } catch (IOException e) {
            throw new RuntimeException("Error opening manifest file: " + outputPath, e);
        }
    }

    public synchronized void write(MethodRecord record) {
        writer.println(gson.toJson(record));
    }

    @Override
    public synchronized void close() {
        writer.close();
    }
}
