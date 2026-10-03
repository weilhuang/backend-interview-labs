import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;
import java.nio.file.*;
import java.util.concurrent.TimeUnit;
/** 可见桥：所有路径显式来自Gradle系统属性，不依赖IDE进程cwd。 */
public class LabCheckTest {
    @Test void yamlContract() throws Exception {
        Path task=Path.of(required("course.taskDir"));
        Path material=Path.of(required("course.materialsDir"));
        var process=new ProcessBuilder(required("course.python"),material.resolve("tests/check_task.py").toString(),"--task","C11-05","--task-dir",task.toString()).directory(task.toFile()).redirectErrorStream(true).start();
        if (!process.waitFor(30,TimeUnit.SECONDS)) { process.destroyForcibly(); fail("YAML checker timeout; INVALID_ENV is not success"); }
        String output=new String(process.getInputStream().readAllBytes(),java.nio.charset.StandardCharsets.UTF_8);
        assertEquals(0,process.exitValue(),output);
        assertTrue(output.contains("YAML_CONTRACT_PASS"),output);
    }
    @Test void javaPolicyAndConfig() throws Exception {
        labs.PolicyContractTest.main(new String[0]);
    }
    private static String required(String key){String value=System.getProperty(key);if(value==null||value.isBlank())throw new IllegalStateException("Missing explicit property: "+key);return value;}
}
