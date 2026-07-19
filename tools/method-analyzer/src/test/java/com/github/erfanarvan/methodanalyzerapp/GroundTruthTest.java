package com.github.erfanarvan.methodanalyzerapp;

import org.junit.jupiter.api.*;
import java.io.*;
import java.nio.file.*;
import java.util.*;

import static org.junit.jupiter.api.Assertions.*;

public class GroundTruthTest {
    private static final String EXPECTED_CSV = "eval/repos/main/main_methods.csv";
    private static final String GENERATED_CSV = "main_methods.csv";

//    @BeforeAll
//    static void runAnalyzer() throws IOException {
//        // Run the tool to generate the CSV output
//        Process process = new ProcessBuilder("java", "-jar", "YourTool.jar", "eval/repos/main").start();
//        try {
//            process.waitFor();
//        } catch (InterruptedException e) {
//            fail("Analyzer execution was interrupted.");
//        }
//    }
//
//    @Test
//    void testCSVOutputMatchesGroundTruth() throws IOException {
//        List<String> expectedLines = Files.readAllLines(Paths.get(EXPECTED_CSV));
//        List<String> generatedLines = Files.readAllLines(Paths.get(GENERATED_CSV));
//
//        assertFalse(expectedLines.isEmpty(), "Expected CSV file is empty!");
//        assertFalse(generatedLines.isEmpty(), "Generated CSV file is empty!");
//        assertEquals(expectedLines.size(), generatedLines.size(), "CSV row counts do not match!");
//
//        for (int i = 0; i < expectedLines.size(); i++) {
//            assertEquals(expectedLines.get(i), generatedLines.get(i), "Mismatch at line " + (i + 1));
//        }
//    }
}
