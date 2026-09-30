import static org.junit.jupiter.api.Assertions.*;

import labs.*;

import org.junit.jupiter.api.*;

import java.sql.*;
import java.util.*;

class StockContractTest {
    @Test
    void rejectsBadInputBeforeOpeningConnection() {
        assertThrows(
                IllegalArgumentException.class,
                () ->
                        StockLab.reserve(
                                () -> {
                                    fail("不应连接");
                                    return null;
                                },
                                "",
                                101,
                                1));
        assertThrows(
                IllegalArgumentException.class, () -> StockLab.reserve(() -> null, "x", 101, 0));
    }

    @Test
    void capacityReturnsAfterConnectionFailure() {
        var gate = new StockLab.Gate(1);
        assertThrows(
                SQLException.class,
                () ->
                        gate.run(
                                () -> {
                                    throw new SQLException("连接失败");
                                },
                                c -> 1));
        assertEquals(1, gate.available());
    }

    @Test
    void invalidGateRejected() {
        assertThrows(IllegalArgumentException.class, () -> new StockLab.Gate(0));
    }
}
