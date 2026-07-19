package com.github.erfanarvan.methodanalyzerapp;

import java.util.Set;

public class TypeUtils {

    private static final Set<String> PRIMITIVE_TYPES = Set.of(
            "byte", "short", "int", "long", "float", "double", "boolean", "char", "void"
    );

    /** Resolution outcomes that mean "we couldn't determine the type" - never treated as standard. */
    private static final Set<String> UNRESOLVED_MARKERS = Set.of(
            "Unresolved", "Unsupported Type", "Timeout", "Wildcard<?>"
    );

    /**
     * Checks if a given (possibly array) type name belongs to the JDK.
     * <p>
     * A type is considered JDK-only if it is a primitive, void, an array of a JDK type,
     * or its fully qualified name starts with one of the standard JDK package prefixes.
     * Anything that failed to resolve is never considered standard: criterion (1) of the
     * snippet-selection filter requires certainty that only JDK types are involved, so an
     * unresolved type must fail closed rather than be silently ignored.
     * </p>
     *
     * @param type The fully qualified or simple type name.
     * @return {@code true} if the type is a standard JDK type, otherwise {@code false}.
     */
    public static boolean isStandardType(String type) {
        if (type == null || type.isEmpty()) {
            return false;
        }

        if (UNRESOLVED_MARKERS.contains(type) || type.startsWith("Error:") || type.startsWith("Generic<")) {
            return false;
        }

        String stripped = type;
        while (stripped.endsWith("[]")) {
            stripped = stripped.substring(0, stripped.length() - 2).trim();
        }

        if (PRIMITIVE_TYPES.contains(stripped)) {
            return true;
        }

        return isStandardLibraryPackage(stripped);
    }

    private static boolean isStandardLibraryPackage(String qname) {
        return qname.startsWith("java.")
                || qname.startsWith("javax.")
                || qname.startsWith("sun.")
                || qname.startsWith("com.sun.")
                || qname.startsWith("jdk.");
    }
}
