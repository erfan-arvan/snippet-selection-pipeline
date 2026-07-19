package com.example;

import org.junit.jupiter.api.Test;

import java.util.List;
import java.util.ArrayList;

public class ExpressionAnalysisSample {  // ✅ Renamed to avoid "test" being skipped

    // ✅ Class fields (should be detected as field accesses)
    private int someField;
    private CustomObject customField;

    // ✅ A method containing various expressions for JavaParser extraction testing
     /**
     * This method contains a variety of expressions for JavaParser analysis.
     * <p>
     * It tests variable declarations, assignments, method calls, field access,
     * loops, conditionals, and object instantiations.
     * </p>
     * 
     * @param param1 An integer parameter used for arithmetic and conditions
     * @param param2 A string parameter used in assignments and expressions
     */ 
     @Test
     public void analyzeExpressions(int param1, String param2) {
        // ✅ Local variable declaration
        int localVar = 42;
        String text = "Hello, JavaParser!";
        CustomObject obj = new CustomObject(param1, param2); // Custom object creation

        // ✅ Assignment expressions
        localVar = localVar + 10;
        text = param2;
        obj.value = 100;

        // ✅ Method calls
        System.out.println("This is a test");
        int length = text.length();
        obj.process();

        // ✅ Object instantiation
        List<String> list = new ArrayList<>();
        list.add("Test");

        // ✅ Field access
        this.someField = 100;
        this.customField = new CustomObject(5, "Field");

        // ✅ Static field access
        HelperClass.staticCounter++;

        // ✅ Conditional expression
        boolean isValid = (length > 5) && param1 > 0;

        // ✅ Loop expression
        for (int i = 0; i < 5; i++) {
            list.add("Item " + i);
        }

        // ✅ Ternary operator
        String message = (param1 > 10) ? "Large" : "Small";

        // ✅ Custom method call
        HelperClass.processStatic();
    }
}

// ✅ Custom type for testing
class CustomObject {
    int value;
    String name;

    public CustomObject(int value, String name) {
        this.value = value;
        this.name = name;
    }

    public void process() {
        System.out.println("Processing: " + name);
    }

    public void x(int x){
        someField=x;
    }
    public void y(){
        System.out.println(String.valueOf(someField));
    }
}

// ✅ Another custom class with a static field and method
class HelperClass {
    public static int staticCounter = 0;

    public static void processStatic() {
        System.out.println("Processing static method");
    }
}

