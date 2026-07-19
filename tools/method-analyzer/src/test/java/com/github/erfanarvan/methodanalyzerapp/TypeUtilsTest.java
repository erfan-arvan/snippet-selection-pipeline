package com.github.erfanarvan.methodanalyzerapp;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

public class TypeUtilsTest {

    @Test
    void testStandardTypes() {
        assertTrue(TypeUtils.isStandardType("int"));
        assertTrue(TypeUtils.isStandardType("java.lang.String"));
        assertTrue(TypeUtils.isStandardType("java.util.List"));
    }

    @Test
    void testCustomTypes() {
        assertFalse(TypeUtils.isStandardType("com.example.MyClass"));
        assertFalse(TypeUtils.isStandardType("CustomType"));
    }

    @Test
    void testNullOrEmptyTypes() {
        assertFalse(TypeUtils.isStandardType(null));
        assertFalse(TypeUtils.isStandardType(""));
    }
}
