package com.github.erfanarvan.methodanalyzerapp;

import com.github.javaparser.StaticJavaParser;
import com.github.javaparser.ast.CompilationUnit;
import com.github.javaparser.ast.body.MethodDeclaration;
import com.github.javaparser.ast.body.TypeDeclaration;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;

/**
 * Exercises the same lookup logic ResolveMethodSignature's main() drives, directly (not via a
 * subprocess), covering: a plain top-level class, a method defined in a nested class (the real
 * bug this tool exists to fix - see Guava's MinMaxPriorityQueue.Heap#crossOverUp), and an
 * ambiguous match that must be refused rather than guessed.
 */
public class ResolveMethodSignatureTest {

    /** Mirrors main()'s search: find the unique (type, method) match, or null if none/ambiguous. */
    private static MethodDeclaration findUnique(CompilationUnit cu, String className, String methodName, int paramCount,
                                                 TypeDeclaration<?>[] matchedTypeOut) {
        List<MethodDeclaration> matches = new ArrayList<>();
        TypeDeclaration<?> matchedType = null;
        for (TypeDeclaration<?> type : cu.findAll(TypeDeclaration.class)) {
            if (!type.getNameAsString().equals(className)) continue;
            for (MethodDeclaration method : type.getMethods()) {
                if (method.getNameAsString().equals(methodName) && method.getParameters().size() == paramCount) {
                    matches.add(method);
                    matchedType = type;
                }
            }
        }
        if (matches.size() != 1) return null;
        matchedTypeOut[0] = matchedType;
        return matches.get(0);
    }

    @Test
    void findsMethodInTopLevelClass(@TempDir Path tempDir) throws IOException {
        String source = String.join("\n",
                "package com.example;",
                "public class Foo {",
                "    public boolean bar(CharSequence a, CharSequence b) {",
                "        return true;",
                "    }",
                "}");
        Path file = tempDir.resolve("Foo.java");
        Files.writeString(file, source);

        CompilationUnit cu = StaticJavaParser.parse(file);
        TypeDeclaration<?>[] matchedType = new TypeDeclaration<?>[1];
        MethodDeclaration method = findUnique(cu, "Foo", "bar", 2, matchedType);

        assertEquals("com.example.Foo",
                QualifiedNameUtils.fullyQualifiedName("com.example", matchedType[0]));
        assertEquals("CharSequence", method.getParameters().get(0).getType().asString());
    }

    @Test
    void findsMethodInNestedClassWithCorrectQualifiedName(@TempDir Path tempDir) throws IOException {
        // Reproduces the real Guava case: crossOverUp is declared in Heap, a class nested
        // inside MinMaxPriorityQueue - the old xlsx only recorded "Heap", with nothing
        // indicating it's nested inside MinMaxPriorityQueue.
        String source = String.join("\n",
                "package com.google.common.collect;",
                "public class MinMaxPriorityQueue<E> {",
                "    private class Heap {",
                "        void crossOverUp(int x, E y) {",
                "        }",
                "    }",
                "}");
        Path file = tempDir.resolve("MinMaxPriorityQueue.java");
        Files.writeString(file, source);

        CompilationUnit cu = StaticJavaParser.parse(file);
        TypeDeclaration<?>[] matchedType = new TypeDeclaration<?>[1];
        MethodDeclaration method = findUnique(cu, "Heap", "crossOverUp", 2, matchedType);

        assertEquals("com.google.common.collect.MinMaxPriorityQueue.Heap",
                QualifiedNameUtils.fullyQualifiedName("com.google.common.collect", matchedType[0]));
        assertEquals("int", method.getParameters().get(0).getType().asString());
        assertEquals("E", method.getParameters().get(1).getType().asString());
    }

    @Test
    void refusesAmbiguousMatchRatherThanGuessing(@TempDir Path tempDir) throws IOException {
        // Two unrelated nested classes both named "Builder", each with a same-arity "build"
        // method - a real (if rare) case where name + arity alone can't disambiguate.
        String source = String.join("\n",
                "package com.example;",
                "public class Outer {",
                "    class Builder {",
                "        Object build(int x) { return null; }",
                "    }",
                "    class Other {",
                "        class Builder {",
                "            Object build(int x) { return null; }",
                "        }",
                "    }",
                "}");
        Path file = tempDir.resolve("Outer.java");
        Files.writeString(file, source);

        CompilationUnit cu = StaticJavaParser.parse(file);
        TypeDeclaration<?>[] matchedType = new TypeDeclaration<?>[1];
        MethodDeclaration method = findUnique(cu, "Builder", "build", 1, matchedType);

        assertNull(method);
    }
}
