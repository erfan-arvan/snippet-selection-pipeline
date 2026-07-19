package com.github.erfanarvan.methodanalyzerapp;

import com.github.javaparser.Range;
import com.github.javaparser.StaticJavaParser;
import com.github.javaparser.ast.CompilationUnit;
import com.github.javaparser.ast.body.MethodDeclaration;

import java.io.File;
import java.util.List;
import java.util.Optional;

/**
 * Standalone entry point (no symbol resolution needed) used by the packaging stage to re-find
 * a target method's line span inside a Specimin-sliced source file.
 * <p>
 * Specimin preserves the target method's own signature and body verbatim, but the surrounding
 * file changes shape (imports, sibling members stubbed out, etc.), so the original line
 * numbers from the method-filtering manifest no longer apply after slicing. This locates the
 * method again by name + parameter count within the sliced file and prints its new line span,
 * which the packaged snippet's metadata needs in order to classify Checker Framework
 * diagnostics as "on the target method" vs "elsewhere in the slice".
 * <p>
 * Usage: {@code java -cp method-analyzer-all.jar com.github.erfanarvan.methodanalyzerapp.LocateMethod <file> <methodName> <paramCount>}
 * Prints "{@code startLine,endLine}" (1-indexed, inclusive) to stdout and exits 0 on success,
 * or prints nothing and exits 1 if no matching method is found.
 */
public class LocateMethod {
    public static void main(String[] args) {
        if (args.length != 3) {
            System.err.println("Usage: LocateMethod <file> <methodName> <paramCount>");
            System.exit(2);
        }

        File file = new File(args[0]);
        String methodName = args[1];
        int paramCount = Integer.parseInt(args[2]);

        try {
            CompilationUnit cu = StaticJavaParser.parse(file);
            List<MethodDeclaration> methods = cu.findAll(MethodDeclaration.class);

            Optional<MethodDeclaration> match = methods.stream()
                    .filter(m -> m.getNameAsString().equals(methodName) && m.getParameters().size() == paramCount)
                    .findFirst();

            if (match.isEmpty()) {
                System.err.println("No method named '" + methodName + "' with " + paramCount + " parameter(s) found in " + file);
                System.exit(1);
                return;
            }

            Range range = match.get().getRange().orElse(null);
            if (range == null) {
                System.err.println("Method found but has no source range: " + methodName);
                System.exit(1);
                return;
            }

            System.out.println(range.begin.line + "," + range.end.line);
            System.exit(0);
        } catch (Exception e) {
            System.err.println("Error parsing " + file + ": " + e.getMessage());
            System.exit(1);
        }
    }
}
