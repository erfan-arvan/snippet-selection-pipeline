package com.github.erfanarvan.methodanalyzerapp;

import org.junit.jupiter.api.*;
import java.io.*;
import java.nio.file.*;

import static org.junit.jupiter.api.Assertions.*;

public class CSVWriterTest {
    private static final String OUTPUT_DIR = "results";
    private static final String TEST_CSV = OUTPUT_DIR + "/test_output.csv";
    private CSVWriter writer;

    @BeforeEach
    void setUp() throws IOException {
        // ensure the results directory exists before writing the CSV
        Files.createDirectories(Paths.get(OUTPUT_DIR));

        // initialize CSVWriter in the results directory
        writer = new CSVWriter("test_output.csv");
    }

    @AfterEach
    void tearDown() {
        writer.close();
        File csvFile = new File(TEST_CSV);
        if (csvFile.exists()) {
            csvFile.delete();
        }
    }

    @Test
    void testWriteAndReadCSV() throws IOException {
        // write a test row to the CSV
        writer.write("testMethod,path/to/File,TestClass,test.package,void");
        writer.close();

        System.out.println("Checking CSV at path: " + TEST_CSV);

        // ensure file exists before reading
        File csvFile = new File(TEST_CSV);
        assertTrue(csvFile.exists(), "CSV file should be created at " + csvFile.getAbsolutePath());

        // read the CSV file to verify content
        BufferedReader reader = new BufferedReader(new FileReader(TEST_CSV));
        String header = reader.readLine(); // First line is the CSV header
        String data = reader.readLine();   // Second line should be our test data
        reader.close();

        assertNotNull(header, "CSV header should not be null");
        assertNotNull(data, "CSV data row should not be null");
        assertTrue(data.contains("testMethod"), "CSV should contain testMethod entry");
    }
}
