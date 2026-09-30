import static org.junit.jupiter.api.Assertions.*;

import labs.*;

import org.junit.jupiter.api.*;

import java.sql.*;
import java.util.*;

class RecoveryContractTest {
    @Test
    void relaxedSettingsDoNotMeanSynchronousLocalLogs() {
        assertTrue(new RecoveryLab.Policy(1, 1, true).strictLocalCommit());
        assertFalse(new RecoveryLab.Policy(2, 1, true).strictLocalCommit());
        assertFalse(new RecoveryLab.Policy(1, 0, true).strictLocalCommit());
        assertFalse(new RecoveryLab.Policy(1, 1, false).strictLocalCommit());
    }
}
