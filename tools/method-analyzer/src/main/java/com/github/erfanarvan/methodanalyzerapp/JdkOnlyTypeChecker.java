package com.github.erfanarvan.methodanalyzerapp;

import com.github.javaparser.ast.body.MethodDeclaration;
import com.github.javaparser.ast.body.Parameter;
import com.github.javaparser.ast.body.VariableDeclarator;
import com.github.javaparser.ast.expr.CastExpr;
import com.github.javaparser.ast.expr.Expression;
import com.github.javaparser.ast.expr.FieldAccessExpr;
import com.github.javaparser.ast.expr.MethodCallExpr;
import com.github.javaparser.ast.expr.NameExpr;
import com.github.javaparser.ast.expr.ObjectCreationExpr;
import com.github.javaparser.resolution.declarations.ResolvedMethodDeclaration;
import com.github.javaparser.resolution.declarations.ResolvedValueDeclaration;
import com.github.javaparser.resolution.types.ResolvedType;

import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

/**
 * Evaluates criterion (1) from the paper's §9.3 method filter: "all types used in the method
 * signature and body must come exclusively from the JDK". This requires more than checking
 * whether the method overrides a java.* method - a call like {@code MyUtils.foo()} that
 * returns an {@code int} would otherwise slip through, even though {@code MyUtils} is a
 * project-internal dependency. So this collects and checks:
 * <ul>
 *   <li>every parameter type and the return type</li>
 *   <li>every local variable's declared type</li>
 *   <li>the resolved type of every expression that can introduce a non-JDK dependency
 *       (method calls, object creation, field access, casts, bare names)</li>
 *   <li>the *declaring type* of every called method / accessed field, since the value it
 *       produces can be JDK-typed even when the thing that declares it is not</li>
 * </ul>
 * Any type that fails to resolve is treated as non-JDK (fail closed), matching the
 * project-level decision to treat unresolved symbols conservatively rather than ignore them.
 */
public class JdkOnlyTypeChecker {

    private static final int TIMEOUT_MS = 500;

    private final ExecutorService executor;

    public JdkOnlyTypeChecker(ExecutorService sharedExecutor) {
        this.executor = sharedExecutor;
    }

    public static class Result {
        public final boolean allJdk;
        public final List<String> offendingTypes;

        Result(boolean allJdk, List<String> offendingTypes) {
            this.allJdk = allJdk;
            this.offendingTypes = offendingTypes;
        }
    }

    public Result check(MethodDeclaration method) {
        Set<String> offenders = new LinkedHashSet<>();

        for (Parameter p : method.getParameters()) {
            checkTypeString(withTimeout(() -> p.getType().resolve().describe()), offenders);
        }

        checkTypeString(withTimeout(() -> method.getType().resolve().describe()), offenders);

        for (VariableDeclarator vd : method.findAll(VariableDeclarator.class)) {
            checkTypeString(withTimeout(() -> vd.getType().resolve().describe()), offenders);
        }

        for (Expression exp : method.findAll(Expression.class)) {
            if (!isInterestingExpression(exp)) {
                continue;
            }
            checkTypeString(withTimeout(() -> describeResolvedType(exp)), offenders);

            if (exp instanceof MethodCallExpr) {
                checkTypeString(withTimeout(() -> {
                    ResolvedMethodDeclaration resolved = ((MethodCallExpr) exp).resolve();
                    return resolved.declaringType().getQualifiedName();
                }), offenders);
            } else if (exp instanceof FieldAccessExpr || exp instanceof NameExpr) {
                checkTypeString(withTimeout(() -> {
                    ResolvedValueDeclaration resolved = exp instanceof FieldAccessExpr
                            ? ((FieldAccessExpr) exp).resolve()
                            : ((NameExpr) exp).resolve();
                    if (resolved.isField()) {
                        return resolved.asField().declaringType().getQualifiedName();
                    }
                    return null; // local variables / parameters: no separate declaring type to check
                }), offenders);
            }
        }

        return new Result(offenders.isEmpty(), new ArrayList<>(offenders));
    }

    private boolean isInterestingExpression(Expression exp) {
        return exp instanceof MethodCallExpr
                || exp instanceof ObjectCreationExpr
                || exp instanceof FieldAccessExpr
                || exp instanceof NameExpr
                || exp instanceof CastExpr;
    }

    private String describeResolvedType(Expression exp) {
        ResolvedType resolvedType = exp.calculateResolvedType();
        if (resolvedType.isPrimitive()) return resolvedType.asPrimitive().describe();
        if (resolvedType.isVoid()) return "void";
        if (resolvedType.isArray()) return resolvedType.asArrayType().describe();
        if (resolvedType.isReferenceType()) return resolvedType.asReferenceType().getQualifiedName();
        return resolvedType.describe();
    }

    private void checkTypeString(String resolved, Set<String> offenders) {
        if (resolved == null) {
            return; // nothing meaningful to check (e.g. a local variable/parameter reference)
        }
        if (!TypeUtils.isStandardType(resolved)) {
            offenders.add(resolved);
        }
    }

    /**
     * Runs a resolution call with a short timeout so a single pathological expression can't
     * hang the whole filtering run. Any failure (unsolved symbol, timeout, unsupported
     * operation) resolves to a sentinel string that {@link TypeUtils#isStandardType} always
     * rejects, so failures fail closed instead of being silently skipped.
     * <p>
     * Uses the shared executor passed at construction time rather than spinning up a new
     * thread pool per call - across a large repo this method runs for every expression in
     * every candidate method, so per-call thread creation would dominate runtime.
     */
    private String withTimeout(Callable<String> resolution) {
        Future<String> future = executor.submit(resolution);
        try {
            return future.get(TIMEOUT_MS, TimeUnit.MILLISECONDS);
        } catch (TimeoutException e) {
            future.cancel(true);
            return "Timeout";
        } catch (Exception e) {
            return "Unresolved";
        }
    }
}
