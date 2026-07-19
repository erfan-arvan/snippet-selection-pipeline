package com.github.erfanarvan.methodanalyzerapp;

import com.github.javaparser.ast.Node;
import com.github.javaparser.ast.body.ClassOrInterfaceDeclaration;
import com.github.javaparser.ast.body.TypeDeclaration;

import java.util.ArrayDeque;
import java.util.Deque;
import java.util.Optional;

/**
 * Computes fully-qualified class names by walking the enclosing-type chain, so that methods
 * declared in nested/inner classes get a correct "Outer.Inner" name instead of just "Inner".
 */
public class QualifiedNameUtils {

    /**
     * Builds the dot-joined simple-name chain for a (possibly nested) type, e.g. "Outer.Inner".
     */
    public static String enclosingTypeChain(TypeDeclaration<?> type) {
        Deque<String> names = new ArrayDeque<>();
        Node current = type;
        while (current instanceof TypeDeclaration) {
            names.addFirst(((TypeDeclaration<?>) current).getNameAsString());
            Optional<Node> parent = current.getParentNode();
            if (parent.isEmpty()) {
                break;
            }
            current = parent.get();
        }
        return String.join(".", names);
    }

    /**
     * Builds the fully qualified name (package + enclosing-type chain) for a type.
     */
    public static String fullyQualifiedName(String packageName, TypeDeclaration<?> type) {
        String chain = enclosingTypeChain(type);
        if (packageName == null || packageName.isEmpty()) {
            return chain;
        }
        return packageName + "." + chain;
    }

    /** Convenience overload for the common case of a class/interface declaration. */
    public static String fullyQualifiedName(String packageName, ClassOrInterfaceDeclaration clazz) {
        return fullyQualifiedName(packageName, (TypeDeclaration<?>) clazz);
    }
}
