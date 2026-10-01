import static org.junit.jupiter.api.Assertions.*;

import labs.*;

import org.junit.jupiter.api.*;

import java.sql.*;
import java.util.*;

class LockContractTest {
    @Test
    void errorClassificationDoesNotRetryUnknownCommit() {
        assertTrue(LockLab.retryable(new SQLException("死锁", "40001", 1213)));
        assertTrue(LockLab.retryable(new SQLException("等待超时", "HY000", 1205)));
        assertFalse(LockLab.retryable(new SQLException("连接中断", "08006", 0)));
        assertFalse(LockLab.retryable(new SQLException("重复键", "23000", 1062)));
    }

    @Test
    void retryBudgetIsBounded() {
        assertThrows(IllegalArgumentException.class, () -> LockLab.retry(() -> null, 0, c -> null));
    }
}
