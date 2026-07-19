package com.github.erfanarvan.methodanalyzerapp;

import com.github.javaparser.ast.body.MethodDeclaration;
import com.github.javaparser.ast.stmt.Statement;
import com.github.javaparser.ast.Node;
import java.util.List;

public class MethodLineCounter {

    // not sure about this! there are a lot of things to consider here.
    public static int[] countMethodLines(MethodDeclaration method) {
        if (!method.getBody().isPresent()) {
            return new int[]{0, 0}; // No method body
        }

        // get all statements inside the method body
        List<Statement> statements = method.getBody().get().getStatements();

        // count raw lines
        int rawLines = statements.stream()
                .map(stmt -> stmt.toString().split("\n").length)
                .reduce(0, Integer::sum);

        // count non-empty, non-comment lines
        int nonEmptyLines = 0;
        boolean inMultilineComment = false;

        for (Statement stmt : statements) {
            String[] lines = stmt.toString().split("\n");

            for (String line : lines) {
                String trimmed = line.trim();

                // detect and skip multiline comments (/* ... */)
                if (trimmed.startsWith("/*")) {
                    inMultilineComment = true;
                }
                if (inMultilineComment) {
                    if (trimmed.endsWith("*/")) {
                        inMultilineComment = false;
                    }
                    continue;
                }

                // skip single-line comments
                if (trimmed.startsWith("//")) {
                    continue;
                }

                // if it's a meaningful line of code, count it
                if (!trimmed.isEmpty()) {
                    nonEmptyLines++;
                }
            }
        }

        return new int[]{rawLines, nonEmptyLines};
    }
}
