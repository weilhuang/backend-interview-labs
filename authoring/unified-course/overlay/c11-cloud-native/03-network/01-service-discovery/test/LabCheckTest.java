import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.Timeout;
import static org.junit.jupiter.api.Assertions.*;
import java.nio.file.*;

/** Visible bridge to the existing shared 15-case policy contract. No Docker/Redis runtime claim. */
public class LabCheckTest {
    @Test
    @Timeout(value = 10, threadMode = Timeout.ThreadMode.SEPARATE_THREAD)
    void policyContract() throws Exception {
        assertEquals("C11-03", required("course.taskId"), "Wrong task adapter");
        assertTrue(Files.isDirectory(Path.of(required("course.taskDir"))), "Missing task directory");
        assertTrue(Files.isDirectory(Path.of(required("course.materialsDir"))), "Missing shared material directory");
        // This task's learner class replaces precisely one shared class; the other policy is the reference.
        labs.PolicyContractTest.main(new String[0]);
    }
    private static String required(String key) {
        String value = System.getProperty(key);
        if (value == null || value.isBlank()) throw new IllegalStateException("Missing explicit property: " + key);
        return value;
    }
}
