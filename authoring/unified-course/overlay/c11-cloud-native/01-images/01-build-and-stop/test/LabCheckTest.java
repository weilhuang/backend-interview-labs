import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.Timeout;
import static org.junit.jupiter.api.Assertions.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.util.concurrent.TimeUnit;
import java.util.regex.Pattern;

/** Visible native bridge. Structural source evidence only; real Docker remains a separate gate. */
public class LabCheckTest {
    @Test
    @Timeout(value = 40, threadMode = Timeout.ThreadMode.SEPARATE_THREAD)
    void dockerfileStructuralContract() throws Exception {
        assertEquals("C11-01", required("course.taskId"), "Wrong task adapter");
        Path task = Path.of(required("course.taskDir"));
        Path material = Path.of(required("course.materialsDir"));
        assertTrue(Files.isDirectory(task), "Missing task directory");
        assertTrue(Files.isDirectory(material), "Missing shared materials directory");
        Path checker = material.resolve("tests/check_task.py");
        assertTrue(Files.isRegularFile(checker), "Missing structural checker; INVALID_ENV is not PASS");
        // A file sink is drained by the OS. Waiting before reading a PIPE could deadlock on large output.
        Path outputFile = Files.createTempFile("c11-01-structural-", ".log");
        Process process = null;
        try {
            process = new ProcessBuilder(required("course.python"), checker.toString(),
                    "--task", "C11-01", "--task-dir", task.toString(),
                    "--materials-dir", material.toString())
                    .directory(task.toFile()).redirectErrorStream(true).redirectOutput(outputFile.toFile()).start();
            assertTrue(process.waitFor(30, TimeUnit.SECONDS),
                    "Structural checker timed out; missing environment or timeout is never PASS");
            long size = Files.size(outputFile);
            assertTrue(size <= 1024 * 1024, "Checker output exceeded diagnostic bound");
            String output = Files.readString(outputFile, StandardCharsets.UTF_8);
            assertEquals(0, process.exitValue(), output);
            var marker = Pattern.compile("(?m)^C11_DOCKERFILE_CONTRACT_PASS cases=([1-9][0-9]*) scope=STRUCTURAL_ONLY docker_runtime=NOT_RUN$").matcher(output);
            assertTrue(marker.find(), "Missing nonzero structural test witness:\n" + output);
            assertEquals(8, Integer.parseInt(marker.group(1)), "Incomplete structural contract");
            assertFalse(marker.find(), "Ambiguous repeated checker result");
        } finally {
            if (process != null && process.isAlive()) {
                // Only this owned checker and its descendants are terminated.
                process.descendants().forEach(ProcessHandle::destroyForcibly);
                process.destroyForcibly();
                process.waitFor(2, TimeUnit.SECONDS);
            }
            Files.deleteIfExists(outputFile);
        }
    }
    private static String required(String key) {
        String value = System.getProperty(key);
        if (value == null || value.isBlank()) throw new IllegalStateException("Missing explicit property: " + key);
        return value;
    }
}
