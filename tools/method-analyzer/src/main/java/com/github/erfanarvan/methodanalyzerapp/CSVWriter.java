package com.github.erfanarvan.methodanalyzerapp;


import java.io.*;


public class CSVWriter {
    private final PrintWriter writer;
    private static final String OUTPUT_DIR = "results";


    /**
     * Creates a CSVWriter instance to write data into a CSV file.
     * <p>
     * This constructor initializes a CSV file with the specified name and writes the header row.
     * If an existing file with the same name is found, it is deleted before creating a new one.
     * </p>
     *
     * @param fileName The name of the CSV file to be created and written to.
     * @throws RuntimeException If an error occurs while opening the file for writing.
     */
    public CSVWriter(String fileName) {
        File outputDir = new File(OUTPUT_DIR);

        // ensure the results directory exists before writing the CSV file
        if (!outputDir.exists()) {
            if (outputDir.mkdirs()) {
                System.out.println("Created directory: " + OUTPUT_DIR);
            } else {
                throw new RuntimeException("Failed to create directory: " + OUTPUT_DIR);
            }
        }

        String filePath = OUTPUT_DIR + "/" + fileName;
        // Delete file if it exists before creating a new one
        File file = new File(filePath);
        if (file.exists()) {
            file.delete(); // Remove old file
            System.out.println("Deleted existing CSV file: " + filePath);
        }

        try {
            writer = new PrintWriter(new FileWriter(filePath, true));
            writer.println("Method,Path,Class,Package,ReturnType,isFinal," +
                    "isAbstract,isStatic,NumParams,ParamTypes,AccessModifier," +
                    "Annotations,Javadoc,RawLoc,CleanLoc,AllTypesJdk," +
                    "PassesAllCriteria");
            System.out.println("CSV file created at: " + filePath);
        } catch (IOException e) {
            throw new RuntimeException("Error opening CSV file: " + filePath, e);
        }
    }

    /**
     * Writes a single line of data to the CSV file.
     *
     * @param data The CSV-formatted string to be written as a new row.
     */
    public void write(String data) {
        writer.println(data);
    }

    /**
     * Closes the CSV file writer.
     * <p>
     * This method should be called once writing to the CSV file is completed
     * to ensure all buffered data is flushed and resources are released.
     * </p>
     */
    public void close() {
        writer.close();
    }

    /**
     * Sanitizes a string for safe inclusion in a CSV file.
     * <p>
     * This method removes or replaces problematic characters such as newlines, carriage returns,
     * double quotes, semicolons, and commas to prevent CSV formatting issues. It also trims
     * unnecessary spaces.
     * </p>
     *
     * @param value The input string to be sanitized.
     * @return A sanitized string that is safe to include in a CSV file.
     */
    public static String sanitizeForCSV(String value) {
        if (value == null || value.trim().isEmpty()) return ""; // Keep empty values clean
        return value.replace("\n", " ")  // Remove newlines
                .replace("\r", " ")  // Remove carriage returns (for Windows)
                .replace("\"", "\"\"")  // Escape double quotes properly for CSV format
                .replace(";", " ")  // Replace semicolons (avoid breaking fields)
                .replace(",", " ")  // Replace commas (avoid breaking CSV)
                .replace("(", " op ")  // Replace opening parentheses
                .replace(")", " cp ")  // Replace closing parentheses
                .replace("{", " ocb ")  // Replace opening curly braces
                .replace("}", " ccb ")  // Replace closing curly braces
                .replace("[", " ob ")  // Replace opening brackets
                .replace("]", " cb ")  // Replace closing brackets
                .trim();
    }
}
