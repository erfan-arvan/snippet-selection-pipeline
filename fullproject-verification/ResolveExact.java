import com.github.javaparser.StaticJavaParser;
import com.github.javaparser.ast.CompilationUnit;
import com.github.javaparser.ast.Node;
import com.github.javaparser.ast.body.MethodDeclaration;
import com.github.javaparser.ast.body.TypeDeclaration;

import java.io.File;
import java.util.*;
import java.util.stream.Collectors;

/**
 * Like the pipeline's ResolveMethodSignature / LocateMethod (same JavaParser calls, same output format),
 * but for overloaded methods it picks the exact overload instead of giving up or taking the first one.
 * Used only by slice_package_exact.py (the original-warnings runs); the pipeline itself is unchanged.
 *
 *   resolve <file> <simpleClassName> <methodName> <paramCount> <endLine>
 *       prints {"qualifiedClassName": ..., "paramTypes": [...]}; among overloads with the same name and
 *       parameter count, the one whose declaration ends on <endLine> (the method that holds the warning).
 *   locate <file> <methodName> <paramCount> [paramType ...]
 *       prints "begin,end" of the method; among overloads, the one whose parameter types (as written)
 *       equal the given ones.
 * Run with: java -cp <method-analyzer-all.jar> ResolveExact.java ...   (exit 1 + stderr when not unique)
 */
public class ResolveExact {
    static String chain(TypeDeclaration<?> type) {            // same as QualifiedNameUtils.enclosingTypeChain
        Deque<String> names = new ArrayDeque<>();
        Node current = type;
        while (current instanceof TypeDeclaration) {
            names.addFirst(((TypeDeclaration<?>) current).getNameAsString());
            Optional<Node> parent = current.getParentNode();
            if (parent.isEmpty()) break;
            current = parent.get();
        }
        return String.join(".", names);
    }

    static boolean hasAncestorNamed(TypeDeclaration<?> type, String name) {
        return type.getParentNode().filter(TypeDeclaration.class::isInstance).map(TypeDeclaration.class::cast)
                .map(p -> p.getNameAsString().equals(name) || hasAncestorNamed(p, name)).orElse(false);
    }

    static List<String> types(MethodDeclaration m) {
        return m.getParameters().stream().map(p -> p.getType().asString()).collect(Collectors.toList());
    }

    static String json(String s) {
        StringBuilder b = new StringBuilder("\"");
        for (char c : s.toCharArray()) {
            if (c == '"' || c == '\\') b.append('\\').append(c);
            else if (c < 0x20) b.append(String.format("\\u%04x", (int) c));
            else b.append(c);
        }
        return b.append('"').toString();
    }

    static void fail(String msg) {
        System.err.println(msg);
        System.exit(1);
    }

    public static void main(String[] a) throws Exception {
        CompilationUnit cu = StaticJavaParser.parse(new File(a[1]));
        if (a[0].equals("resolve")) {
            String cls = a[2], name = a[3];
            int n = Integer.parseInt(a[4]), endLine = Integer.parseInt(a[5]);
            String pkg = cu.getPackageDeclaration().map(pd -> pd.getName().asString()).orElse("");
            List<Object[]> matches = new ArrayList<>();
            for (int pass = 0; pass < 2 && matches.isEmpty(); pass++) {   // pass 1: nested under cls (as the pipeline)
                for (TypeDeclaration<?> t : cu.findAll(TypeDeclaration.class)) {
                    boolean ok = pass == 0 ? t.getNameAsString().equals(cls)
                                           : !t.getNameAsString().equals(cls) && hasAncestorNamed(t, cls);
                    if (!ok) continue;
                    for (MethodDeclaration m : t.getMethods())
                        if (m.getNameAsString().equals(name) && m.getParameters().size() == n) matches.add(new Object[]{t, m});
                }
            }
            if (matches.size() > 1)
                matches = matches.stream().filter(x -> ((MethodDeclaration) x[1]).getRange().map(r -> r.end.line == endLine).orElse(false))
                        .collect(Collectors.toList());
            if (matches.size() != 1) fail(matches.size() + " methods '" + name + "' with " + n + " parameter(s) ending on line " + endLine + " in " + a[1]);
            TypeDeclaration<?> t = (TypeDeclaration<?>) matches.get(0)[0];
            String q = pkg.isEmpty() ? chain(t) : pkg + "." + chain(t);
            System.out.println("{\"qualifiedClassName\":" + json(q) + ",\"paramTypes\":["
                    + types((MethodDeclaration) matches.get(0)[1]).stream().map(ResolveExact::json).collect(Collectors.joining(",")) + "]}");
        } else if (a[0].equals("locate")) {
            String name = a[2];
            int n = Integer.parseInt(a[3]);
            List<String> want = Arrays.asList(a).subList(4, a.length);
            List<MethodDeclaration> ms = cu.findAll(MethodDeclaration.class).stream()
                    .filter(m -> m.getNameAsString().equals(name) && m.getParameters().size() == n).collect(Collectors.toList());
            if (ms.size() > 1 && !want.isEmpty())
                ms = ms.stream().filter(m -> types(m).equals(want)).collect(Collectors.toList());
            if (ms.size() != 1 || ms.get(0).getRange().isEmpty()) fail(ms.size() + " methods '" + name + "' " + want + " in " + a[1]);
            System.out.println(ms.get(0).getRange().get().begin.line + "," + ms.get(0).getRange().get().end.line);
        } else {
            fail("usage: resolve|locate ...");
        }
    }
}
