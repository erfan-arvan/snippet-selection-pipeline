package com.github.erfanarvan.methodanalyzerapp;

import com.github.javaparser.StaticJavaParser;
import com.github.javaparser.ast.CompilationUnit;
import com.github.javaparser.ast.body.MethodDeclaration;
import com.github.javaparser.ast.body.TypeDeclaration;
import com.google.gson.Gson;
import com.google.gson.GsonBuilder;

import java.io.File;
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Collectors;

/**
 * Standalone entry point (no symbol resolution needed) used to recover a correct Specimin
 * --targetMethod signature for a candidate imported from the legacy xlsx export, whose
 * ParamTypes/Class columns can be wrong: fully-qualified types Specimin won't match against
 * source (it matches type names as spelled, respecting imports - see the live MethodExtractor's
 * describeType(), which resolves to fully-qualified names and has the same latent mismatch),
 * the literal "Unresolved" placeholder for types the old tool couldn't resolve, or a nested
 * class's bare simple name with no indication that it's nested.
 * <p>
 * This deliberately never resolves types - it just reads the parameter list as written in the
 * source - and searches every type declaration in the file (not just top-level ones), so a
 * class doesn't need to be known in advance to be nested: whichever declaration matches by
 * simple name and method arity is used, and its enclosing-type chain (via
 * {@link QualifiedNameUtils}) gives the correct nested-qualified class name for free.
 * <p>
 * Usage: {@code java -cp method-analyzer-all.jar com.github.erfanarvan.methodanalyzerapp.ResolveMethodSignature <file> <simpleClassName> <methodName> <paramCount>}
 * Prints a JSON object {@code {"qualifiedClassName": ..., "paramTypes": [...]}} to stdout and
 * exits 0 on an unambiguous match, or prints an error to stderr and exits 1 if the method isn't
 * found or the match is ambiguous (never guesses).
 */
public class ResolveMethodSignature {

    static class Result {
        String qualifiedClassName;
        List<String> paramTypes;
    }

    public static void main(String[] args) {
        if (args.length != 4) {
            System.err.println("Usage: ResolveMethodSignature <file> <simpleClassName> <methodName> <paramCount>");
            System.exit(2);
        }

        File file = new File(args[0]);
        String className = args[1];
        String methodName = args[2];
        int paramCount = Integer.parseInt(args[3]);

        try {
            CompilationUnit cu = StaticJavaParser.parse(file);
            String packageName = cu.getPackageDeclaration()
                    .map(pd -> pd.getName().asString())
                    .orElse("");

            List<MethodDeclaration> matches = new ArrayList<>();
            TypeDeclaration<?> matchedType = null;

            for (TypeDeclaration<?> type : cu.findAll(TypeDeclaration.class)) {
                if (!type.getNameAsString().equals(className)) {
                    continue;
                }
                for (MethodDeclaration method : type.getMethods()) {
                    if (method.getNameAsString().equals(methodName) && method.getParameters().size() == paramCount) {
                        matches.add(method);
                        matchedType = type;
                    }
                }
            }

            if (matches.isEmpty()) {
                System.err.println("No method '" + methodName + "' with " + paramCount
                        + " parameter(s) found in class '" + className + "' in " + file);
                System.exit(1);
                return;
            }
            if (matches.size() > 1) {
                System.err.println("Ambiguous: found " + matches.size() + " matching methods named '"
                        + methodName + "' with " + paramCount + " parameter(s) in class '" + className
                        + "' in " + file);
                System.exit(1);
                return;
            }

            MethodDeclaration method = matches.get(0);
            Result result = new Result();
            result.qualifiedClassName = QualifiedNameUtils.fullyQualifiedName(packageName, matchedType);
            // As-written types (no resolution): Specimin matches against source spelling, not
            // fully-qualified names. Varargs are left as their component type - untested against
            // Specimin, not worth guessing at a "..." notation without evidence it wants one.
            result.paramTypes = method.getParameters().stream()
                    .map(p -> p.getType().asString())
                    .collect(Collectors.toList());

            Gson gson = new GsonBuilder().disableHtmlEscaping().create();
            System.out.println(gson.toJson(result));
            System.exit(0);
        } catch (Exception e) {
            System.err.println("Error parsing " + file + ": " + e.getMessage());
            System.exit(1);
        }
    }
}
