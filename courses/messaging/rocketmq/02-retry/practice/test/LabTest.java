import static org.junit.jupiter.api.Assertions.*;

import labs.messaging.Lab;

import org.junit.jupiter.api.Test;

class LabTest {
    @Test
    void 临时失败有上限永久失败直接隔离() {
        assertEquals(Lab.Action.RETRY, Lab.decide(Lab.Failure.TRANSIENT, 1, 3));
        assertEquals(Lab.Action.QUARANTINE, Lab.decide(Lab.Failure.TRANSIENT, 3, 3));
        assertEquals(Lab.Action.QUARANTINE, Lab.decide(Lab.Failure.PERMANENT, 1, 3));
        assertEquals(Lab.Action.ACK, Lab.decide(Lab.Failure.NONE, 4, 3));
        assertThrows(IllegalArgumentException.class, () -> Lab.decide(Lab.Failure.NONE, 0, 3));
    }
}
