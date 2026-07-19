package com.github.erfanarvan.methodanalyzerapp;

import java.util.List;

/**
 * One row of the machine-readable manifest: everything the pipeline needs to know about a
 * single candidate method, including per-criterion detail (not just a final pass/fail) so
 * failures are debuggable downstream instead of being an opaque "filtered out".
 */
public class MethodRecord {
    public String project;
    public String filePath;
    public String packageName;
    public String qualifiedClassName;
    public String methodName;
    public String returnType;
    public List<String> paramTypes;
    public int numParams;
    public boolean isStatic;
    public boolean isFinal;
    public boolean isAbstract;
    public String accessModifier;
    public List<String> annotations;
    public boolean hasJavadoc;
    public String javadoc;
    public int rawLoc;
    public int cleanLoc;
    public int startLine;
    public int endLine;
    public boolean allTypesJdk;
    public List<String> offendingTypes;

    public Criteria criteria;
    public boolean passesAllCriteria;

    /** Ready-to-use Specimin --targetMethod value, e.g. "pkg.Outer.Inner#foo(java.lang.String,int)". */
    public String targetMethodSignature;

    public static class Criteria {
        public boolean isStatic;
        public boolean noAnnotations;
        public boolean hasJavadoc;
        public boolean paramAndReturnOk;
        public boolean locInRange;
        public boolean allTypesJdk;

        public boolean allPass() {
            return isStatic && noAnnotations && hasJavadoc && paramAndReturnOk && locInRange && allTypesJdk;
        }
    }
}
