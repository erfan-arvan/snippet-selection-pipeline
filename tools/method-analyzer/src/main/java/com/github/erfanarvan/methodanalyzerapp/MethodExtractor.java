package com.github.erfanarvan.methodanalyzerapp;

import com.github.javaparser.Range;
import com.github.javaparser.ast.CompilationUnit;
import com.github.javaparser.ast.Modifier;
import com.github.javaparser.ast.body.MethodDeclaration;
import com.github.javaparser.ast.body.TypeDeclaration;
import com.github.javaparser.ast.comments.JavadocComment;
import com.github.javaparser.ast.expr.AnnotationExpr;
import com.github.javaparser.resolution.types.ResolvedType;

import java.io.File;
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;
import java.util.stream.Collectors;

/**
 * Evaluates the six §9.3 method-filtering criteria for every candidate method in a file and
 * emits one {@link MethodRecord} per method to the shared {@link ManifestWriter}, plus a
 * human-readable CSV row for quick inspection.
 */
public class MethodExtractor {

    private static final int TIMEOUT_MS_TYPE = 500;
    private static final int MIN_LOC = 20;
    private static final int MAX_LOC = 30;

    private final File javaFile;
    private final String relativePath;
    private final String projectName;
    private final CompilationUnit cu;
    private final CSVWriter projectWriter;
    private final CSVWriter aggregatedWriter;
    private final ManifestWriter manifestWriter;
    private final ExecutorService executor;
    private final JdkOnlyTypeChecker jdkOnlyTypeChecker;
    private String packageName = "";

    public MethodExtractor(
            File javaFile,
            String relativePath,
            String projectName,
            CompilationUnit cu,
            CSVWriter projectWriter,
            CSVWriter aggregatedWriter,
            ManifestWriter manifestWriter,
            ExecutorService executor
    ) {
        this.javaFile = javaFile;
        this.relativePath = relativePath;
        this.projectName = projectName;
        this.cu = cu;
        this.projectWriter = projectWriter;
        this.aggregatedWriter = aggregatedWriter;
        this.manifestWriter = manifestWriter;
        this.executor = executor;
        this.jdkOnlyTypeChecker = new JdkOnlyTypeChecker(executor);
        this.packageName = cu.getPackageDeclaration().map(pd -> pd.getName().asString()).orElse("");
    }

    /**
     * Extracts and processes all methods from the Java file, writing one manifest record
     * (and one CSV row) per method regardless of whether it ultimately passes the filter -
     * the manifest records per-criterion detail so rejections stay debuggable.
     */
    public void extract() {
        cu.findAll(MethodDeclaration.class).forEach(this::processMethod);
    }

    private void processMethod(MethodDeclaration method) {
        try {
            MethodRecord record = buildRecord(method);
            manifestWriter.write(record);

            String csvLine = String.join(",",
                    CSVWriter.sanitizeForCSV(record.methodName),
                    CSVWriter.sanitizeForCSV(relativePath),
                    CSVWriter.sanitizeForCSV(record.qualifiedClassName),
                    CSVWriter.sanitizeForCSV(record.packageName),
                    CSVWriter.sanitizeForCSV(record.returnType),
                    String.valueOf(record.isFinal),
                    String.valueOf(record.isAbstract),
                    String.valueOf(record.isStatic),
                    String.valueOf(record.numParams),
                    CSVWriter.sanitizeForCSV(String.join("|", record.paramTypes)),
                    CSVWriter.sanitizeForCSV(record.accessModifier),
                    CSVWriter.sanitizeForCSV(String.join("|", record.annotations)),
                    CSVWriter.sanitizeForCSV(record.javadoc),
                    String.valueOf(record.rawLoc),
                    String.valueOf(record.cleanLoc),
                    String.valueOf(record.allTypesJdk),
                    String.valueOf(record.passesAllCriteria)
            );
            projectWriter.write(csvLine);
            aggregatedWriter.write(csvLine);
        } catch (Exception e) {
            System.err.println("Error processing method " + method.getNameAsString() + " in " + javaFile + ": " + e.getMessage());
        }
    }

    private MethodRecord buildRecord(MethodDeclaration method) {
        MethodRecord record = new MethodRecord();
        record.project = projectName;
        record.filePath = relativePath;
        record.packageName = packageName;
        record.qualifiedClassName = method.findAncestor(TypeDeclaration.class)
                .map(t -> QualifiedNameUtils.fullyQualifiedName(packageName, t))
                .orElse("");
        record.methodName = method.getNameAsString();

        record.isStatic = method.getModifiers().contains(Modifier.staticModifier());
        record.isFinal = method.getModifiers().contains(Modifier.finalModifier());
        record.isAbstract = method.getModifiers().contains(Modifier.abstractModifier());
        record.accessModifier = method.getAccessSpecifier().asString();

        record.annotations = method.getAnnotations().stream()
                .map(AnnotationExpr::getNameAsString)
                .collect(Collectors.toList());

        record.hasJavadoc = hasJavadoc(method);
        record.javadoc = getJavadocText(method);

        record.returnType = resolveWithTimeout(() -> describeType(method.getType().resolve()));
        record.paramTypes = method.getParameters().stream()
                .map(p -> resolveWithTimeout(() -> describeType(p.getType().resolve())))
                .collect(Collectors.toList());
        record.numParams = method.getParameters().size();

        int[] loc = MethodLineCounter.countMethodLines(method);
        record.rawLoc = loc[0];
        record.cleanLoc = loc[1];

        Range range = method.getRange().orElse(null);
        record.startLine = range != null ? range.begin.line : -1;
        record.endLine = range != null ? range.end.line : -1;

        JdkOnlyTypeChecker.Result jdkResult = jdkOnlyTypeChecker.check(method);
        record.allTypesJdk = jdkResult.allJdk;
        record.offendingTypes = jdkResult.offendingTypes;

        MethodRecord.Criteria criteria = new MethodRecord.Criteria();
        criteria.isStatic = record.isStatic;
        criteria.noAnnotations = record.annotations.isEmpty();
        criteria.hasJavadoc = record.hasJavadoc;
        criteria.paramAndReturnOk = record.numParams >= 1 && !"void".equals(record.returnType);
        criteria.locInRange = record.cleanLoc >= MIN_LOC && record.cleanLoc <= MAX_LOC;
        criteria.allTypesJdk = record.allTypesJdk;
        record.criteria = criteria;
        record.passesAllCriteria = criteria.allPass();

        // Specimin's --targetMethod format: class.fully.qualified.Name#methodName(Param1Type, Param2Type, ...)
        record.targetMethodSignature = record.qualifiedClassName + "#" + record.methodName
                + "(" + String.join(", ", record.paramTypes) + ")";

        return record;
    }

    private boolean hasJavadoc(MethodDeclaration method) {
        if (method.getJavadoc().isPresent()) {
            return true;
        }
        return method.getComment().isPresent() && method.getComment().get() instanceof JavadocComment;
    }

    /**
     * Extracts the Javadoc comment associated with the given method, falling back to a raw
     * Javadoc-style comment if JavaParser didn't attach it as structured Javadoc.
     */
    private String getJavadocText(MethodDeclaration method) {
        if (method.getJavadoc().isPresent()) {
            return method.getJavadoc().get().getDescription().toText();
        }
        if (method.getComment().isPresent()) {
            var comment = method.getComment().get();
            if (comment instanceof JavadocComment) {
                return ((JavadocComment) comment).parse().getDescription().toText();
            }
        }
        return "";
    }

    private String describeType(ResolvedType resolvedType) {
        if (resolvedType.isPrimitive()) return resolvedType.asPrimitive().describe();
        if (resolvedType.isVoid()) return "void";
        if (resolvedType.isArray()) return resolvedType.asArrayType().describe();
        if (resolvedType.isReferenceType()) return resolvedType.asReferenceType().getQualifiedName();
        return resolvedType.describe();
    }

    private String resolveWithTimeout(Callable<String> resolution) {
        Future<String> future = executor.submit(resolution);
        try {
            return future.get(TIMEOUT_MS_TYPE, TimeUnit.MILLISECONDS);
        } catch (TimeoutException e) {
            future.cancel(true);
            return "Timeout";
        } catch (Exception e) {
            return "Unresolved";
        }
    }
}
