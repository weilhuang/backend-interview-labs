import org.junit.jupiter.api.Test;
import java.nio.file.Path;
import java.time.Duration;
/** Academy仍接收JUnit结果；真正的业务断言保留在可见Go工程中。 */
public class GoContractTest {
 @Test public void goFoundationContract() throws Exception {
  String executable=System.getProperty("go.executable",System.getenv("GO_EXECUTABLE"));
  if(executable==null||executable.isBlank()) throw new IllegalStateException("INVALID_ENV: 设置GO_EXECUTABLE，不能默认调用系统里另一个同名go程序");
  Path project=Path.of(System.getProperty("go.project","go")).toAbsolutePath().normalize();
  Path work=Path.of(System.getProperty("go.work","build/go-check")).toAbsolutePath().normalize();
  GoTestBridge.requirePassed(GoTestBridge.execute(Path.of(executable).toAbsolutePath(),project,work,Duration.ofSeconds(90)));
 }
}
