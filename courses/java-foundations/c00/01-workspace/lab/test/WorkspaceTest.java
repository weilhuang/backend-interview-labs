import static org.junit.jupiter.api.Assertions.*;

import labs.foundation.*;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.Timeout;

import java.util.*;
import java.util.concurrent.*;

@Timeout(5)
class WorkspaceTest {
    @Test
    void normalAndEmpty() {
        assertEquals(
                150,
                Workspace.paidTotal(
                        List.of(
                                new Order("a", "甲", 100, Order.Status.PAID),
                                new Order("b", "乙", 800, Order.Status.PENDING),
                                new Order("c", "甲", 50, Order.Status.PAID))));
        assertEquals(0, Workspace.paidTotal(List.of()));
    }

    @Test
    void invalidAndOverflow() {
        assertThrows(NullPointerException.class, () -> Workspace.paidTotal(null));
        assertThrows(
                NullPointerException.class, () -> Workspace.paidTotal(Arrays.asList((Order) null)));
        assertThrows(
                ArithmeticException.class,
                () ->
                        Workspace.paidTotal(
                                List.of(
                                        new Order("a", "甲", Long.MAX_VALUE, Order.Status.PAID),
                                        new Order("b", "甲", 1, Order.Status.PAID))));
    }
}
