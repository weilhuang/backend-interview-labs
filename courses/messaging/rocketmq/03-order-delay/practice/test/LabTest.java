import static org.junit.jupiter.api.Assertions.*;

import labs.messaging.*;

import org.junit.jupiter.api.Test;

class LabTest {
    @Test
    void 同实体消息组与迟到取消状态机() {
        assertEquals(
                "o1",
                Lab.ordered("topic", new Event("e1", "o1", 1, 0)).getMessageGroup().orElseThrow());
        assertEquals(Lab.OrderState.PAID, Lab.cancelIfUnpaid(Lab.OrderState.PAID));
        assertEquals(Lab.OrderState.CANCELLED, Lab.cancelIfUnpaid(Lab.OrderState.UNPAID));
        assertEquals(Lab.OrderState.CANCELLED, Lab.cancelIfUnpaid(Lab.OrderState.CANCELLED));
    }
}
