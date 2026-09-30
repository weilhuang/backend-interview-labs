package labs.capstone;

import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;

class RecoveryTest {
    @Test
    void 数据库故障不能接单() {
        assertFalse(RecoveryPolicy.decide(false, true, true, true, 0, 10).ready());
    }

    @Test
    void 下游故障预算内接单但明确降级() {
        var d = RecoveryPolicy.decide(true, true, false, false, 9, 10);
        assertTrue(d.ready());
        assertTrue(d.degraded());
    }

    @Test
    void 积压达到阈值立即拒绝新单() {
        assertFalse(RecoveryPolicy.decide(true, true, true, true, 10, 10).ready());
        assertFalse(RecoveryPolicy.decide(true, true, true, true, 11, 10).ready());
    }

    @Test
    void Redis不决定业务事务可用性() {
        var d = RecoveryPolicy.decide(true, false, true, true, 0, 10);
        assertTrue(d.ready());
        assertTrue(d.degraded());
        assertFalse(RecoveryPolicy.decide(true, true, true, true, 0, 10).degraded());
    }

    @Test
    void 非法预算拒绝并且退避有界() {
        assertThrows(
                IllegalArgumentException.class,
                () -> RecoveryPolicy.decide(true, true, true, true, -1, 10));
        assertThrows(
                IllegalArgumentException.class,
                () -> RecoveryPolicy.decide(true, true, true, true, 0, 0));
        assertEquals(250, RecoveryPolicy.retryDelay(0).toMillis());
        assertEquals(16000, RecoveryPolicy.retryDelay(100).toMillis());
        assertThrows(IllegalArgumentException.class, () -> RecoveryPolicy.retryDelay(-1));
    }
}
