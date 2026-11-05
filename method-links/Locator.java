import com.sun.source.tree.*;
import com.sun.source.util.*;
import javax.tools.*;
import java.util.*;

/** Prints one line per method/ctor: file \t qualifiedClass \t methodName \t paramCount \t startLine \t endLine
 * Pure syntactic parse (task.parse(), never .analyze()) - needs no classpath/dependencies,
 * works on any single .java file regardless of which repo it came from. */
public class Locator {
  public static void main(String[] args) throws Exception {
    JavaCompiler jc = ToolProvider.getSystemJavaCompiler();
    StandardJavaFileManager fm = jc.getStandardFileManager(null, null, null);
    for (String f : args) {
      try {
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
              System.out.println(f + "\t" + cls + "\t" + mt.getName() + "\t" + mt.getParameters().size()
                  + "\t" + lm.getLineNumber(s) + "\t" + lm.getLineNumber(e));
              return super.visitMethod(mt, cls);
            }
          }.scan(cu, null);
        }
      } catch (Exception ex) {
        System.err.println("PARSE_ERROR\t" + f + "\t" + ex);
      }
    }
  }
}
