import com.sun.source.tree.*;
import com.sun.source.util.*;
import javax.tools.*;
import java.util.*;
import java.util.stream.*;

/**
 * Used by compare_results.py to find a method's line range in the ORIGINAL source.
 * Prints one line per method/constructor:
 *   file \t qualifiedClass \t methodName \t numParams \t paramType1,paramType2,... \t startLine \t endLine
 * Nested classes are joined with '.'. Constructors are printed as "<init>".
 * Run with: java Locator.java <file.java>...   (JDK >= 17; parse only, nothing is compiled)
 */
public class Locator {
  public static void main(String[] args) throws Exception {
    JavaCompiler jc = ToolProvider.getSystemJavaCompiler();
    StandardJavaFileManager fm = jc.getStandardFileManager(null, null, null);
    for (String f : args) {
      JavacTask task = (JavacTask) jc.getTask(null, fm, d -> {}, List.of("-proc:none"), null,
          fm.getJavaFileObjects(f));
      for (CompilationUnitTree cu : task.parse()) {
        SourcePositions sp = Trees.instance(task).getSourcePositions();
        LineMap lm = cu.getLineMap();
        String pkg = cu.getPackageName() == null ? "" : cu.getPackageName().toString() + ".";
        new TreePathScanner<Void, String>() {
          @Override public Void visitClass(ClassTree ct, String outer) {
            String n = ct.getSimpleName().toString();
            String q = n.isEmpty() ? outer : (outer == null ? pkg + n : outer + "." + n);
            return super.visitClass(ct, q);
          }
          @Override public Void visitMethod(MethodTree mt, String cls) {
            long s = sp.getStartPosition(cu, mt), e = sp.getEndPosition(cu, mt);
            String types = mt.getParameters().stream().map(p -> p.getType().toString().replace("\t", " "))
                .collect(Collectors.joining(","));
            System.out.println(f + "\t" + cls + "\t" + mt.getName() + "\t" + mt.getParameters().size() + "\t"
                + types + "\t" + lm.getLineNumber(s) + "\t" + lm.getLineNumber(e));
            return super.visitMethod(mt, cls);
          }
        }.scan(cu, null);
      }
    }
  }
}
