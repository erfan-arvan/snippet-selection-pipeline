package com.github.erfanarvan.methodanalyzerapp;

import com.google.gson.Gson;
import com.google.gson.JsonObject;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.HashMap;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * End-to-end test of the six §9.3 filtering criteria: runs the real DirectoryProcessor over a
 * small synthetic "project" (no network, no real repos needed) and checks that each criterion
 * is flagged correctly, both individually and in combination, using the JSONL manifest output.
 */
public class MethodExtractorCriteriaTest {

    /** Builds N single-line, JDK-only statements so clean LOC == N exactly. */
    private static String bodyLines(int n) {
        StringBuilder sb = new StringBuilder();
        sb.append("int acc = x;\n");
        for (int i = 1; i < n - 1; i++) {
            sb.append("acc = acc + ").append(i).append(";\n");
        }
        sb.append("return acc;\n");
        return sb.toString();
    }

    private static final String SAMPLE_SOURCE = String.join("\n",
            "public class Sample {",
            "",
            "    /** A method that satisfies all six filtering criteria. */",
            "    public static int goodMethod(int x) {",
            indent(bodyLines(22)),
            "    }",
            "",
            "    /** Too short to satisfy the LOC criterion. */",
            "    public static int tooFewLines(int x) {",
            indent(bodyLines(5)),
            "    }",
            "",
            "    /** Too long to satisfy the LOC criterion. */",
            "    public static int tooManyLines(int x) {",
            indent(bodyLines(35)),
            "    }",
            "",
            "    /** Not static, so fails the isStatic criterion. */",
            "    public int notStatic(int x) {",
            indent(bodyLines(22)),
            "    }",
            "",
            "    /** Has an annotation, so fails the noAnnotations criterion. */",
            "    @Deprecated",
            "    public static int hasAnnotation(int x) {",
            indent(bodyLines(22)),
            "    }",
            "",
            "    public static int noJavadoc(int x) {",
            indent(bodyLines(22)),
            "    }",
            "",
            "    /** Void return, so fails the param/return criterion. */",
            "    public static void voidReturn(int x) {",
            indent(bodyLines(22).replace("return acc;", "acc = acc + 0;")),
            "    }",
            "",
            "    /** No parameters, so fails the param/return criterion. */",
            "    public static int noParams() {",
            indent(bodyLines(22).replace("int acc = x;", "int acc = 0;")),
            "    }",
            "",
            "    /** Calls a project-internal helper, so fails the all-JDK-types criterion",
            "     *  even though the helper's own signature is JDK-typed (int -> int). */",
            "    public static int usesCustomType(int x) {",
            indent(bodyLines(21).replace("int acc = x;", "int acc = CustomHelper.helper(x);")),
            "    }",
            "}"
    );

    private static final String CUSTOM_HELPER_SOURCE = String.join("\n",
            "public class CustomHelper {",
            "    public static int helper(int x) {",
            "        return x + 1;",
            "    }",
            "}"
    );

    private static String indent(String block) {
        StringBuilder sb = new StringBuilder();
        for (String line : block.split("\n")) {
            sb.append("        ").append(line).append("\n");
        }
        return sb.toString().stripTrailing();
    }

    @Test
    void sixCriteriaAreEvaluatedIndependently(@TempDir Path tempDir) throws IOException {
        Path projectDir = tempDir.resolve("repos").resolve("sampleproject");
        Files.createDirectories(projectDir);
        Files.writeString(projectDir.resolve("Sample.java"), SAMPLE_SOURCE);
        Files.writeString(projectDir.resolve("CustomHelper.java"), CUSTOM_HELPER_SOURCE);

        Path manifestPath = tempDir.resolve("manifest.jsonl");

        DirectoryProcessor processor = new DirectoryProcessor(
                tempDir.resolve("repos").toString(),
                manifestPath.toString()
        );
        processor.processProjects();

        Map<String, JsonObject> byMethod = readManifestByMethodName(manifestPath);

        assertTrue(byMethod.containsKey("goodMethod"), "expected goodMethod to be present in manifest");

        JsonObject good = byMethod.get("goodMethod").getAsJsonObject("criteria");
        assertTrue(good.get("isStatic").getAsBoolean());
        assertTrue(good.get("noAnnotations").getAsBoolean());
        assertTrue(good.get("hasJavadoc").getAsBoolean());
        assertTrue(good.get("paramAndReturnOk").getAsBoolean());
        assertTrue(good.get("locInRange").getAsBoolean());
        assertTrue(good.get("allTypesJdk").getAsBoolean());
        assertTrue(byMethod.get("goodMethod").get("passesAllCriteria").getAsBoolean());
        assertEquals(
                "Sample#goodMethod(int)",
                byMethod.get("goodMethod").get("targetMethodSignature").getAsString()
        );

        assertFalse(byMethod.get("tooFewLines").getAsJsonObject("criteria").get("locInRange").getAsBoolean());
        assertFalse(byMethod.get("tooManyLines").getAsJsonObject("criteria").get("locInRange").getAsBoolean());
        assertFalse(byMethod.get("notStatic").getAsJsonObject("criteria").get("isStatic").getAsBoolean());
        assertFalse(byMethod.get("hasAnnotation").getAsJsonObject("criteria").get("noAnnotations").getAsBoolean());
        assertFalse(byMethod.get("noJavadoc").getAsJsonObject("criteria").get("hasJavadoc").getAsBoolean());
        assertFalse(byMethod.get("voidReturn").getAsJsonObject("criteria").get("paramAndReturnOk").getAsBoolean());
        assertFalse(byMethod.get("noParams").getAsJsonObject("criteria").get("paramAndReturnOk").getAsBoolean());

        JsonObject customType = byMethod.get("usesCustomType").getAsJsonObject("criteria");
        assertFalse(customType.get("allTypesJdk").getAsBoolean(),
                "a call to a project-internal helper must fail criterion 1 even though the helper's own signature is JDK-typed");
        assertFalse(byMethod.get("usesCustomType").get("passesAllCriteria").getAsBoolean());

        for (String failing : new String[]{
                "tooFewLines", "tooManyLines", "notStatic", "hasAnnotation",
                "noJavadoc", "voidReturn", "noParams", "usesCustomType"
        }) {
            assertFalse(byMethod.get(failing).get("passesAllCriteria").getAsBoolean(),
                    failing + " should not pass all criteria");
        }
    }

    private Map<String, JsonObject> readManifestByMethodName(Path manifestPath) throws IOException {
        Gson gson = new Gson();
        Map<String, JsonObject> result = new HashMap<>();
        for (String line : Files.readAllLines(manifestPath)) {
            if (line.isBlank()) continue;
            JsonObject obj = gson.fromJson(line, JsonObject.class);
            result.put(obj.get("methodName").getAsString(), obj);
        }
        return result;
    }
}
