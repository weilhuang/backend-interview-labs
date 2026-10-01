import static org.junit.jupiter.api.Assertions.*;

import labs.*;

import org.junit.jupiter.api.*;

import java.sql.*;
import java.util.*;

class OrderContractTest {
    @Test
    void exactMoney() {
        assertEquals(1500, OrderQueries.cents("15.00"));
        assertEquals(1, OrderQueries.cents("0.01"));
    }

    @Test
    void refusesLostFraction() {
        assertThrows(ArithmeticException.class, () -> OrderQueries.cents("0.001"));
    }

    @Test
    void refusesOverflow() {
        assertThrows(
                ArithmeticException.class, () -> OrderQueries.cents("999999999999999999999999"));
    }

    @Test
    void rollbackFailureClosesRatherThanAccidentallyCommitting() throws Exception {
        var events = new java.util.ArrayList<String>();
        Connection c =
                (Connection)
                        java.lang.reflect.Proxy.newProxyInstance(
                                getClass().getClassLoader(),
                                new Class[] {Connection.class},
                                (proxy, method, args) -> {
                                    return switch (method.getName()) {
                                        case "getAutoCommit" -> true;
                                        case "setAutoCommit" -> {
                                            events.add("auto=" + args[0]);
                                            yield null;
                                        }
                                        case "rollback" -> {
                                            throw new SQLException("回滚连接已失效");
                                        }
                                        case "close" -> {
                                            events.add("close");
                                            yield null;
                                        }
                                        default ->
                                                throw new UnsupportedOperationException(
                                                        method.getName());
                                    };
                                });
        IllegalStateException primary =
                assertThrows(
                        IllegalStateException.class,
                        () ->
                                Db.transaction(
                                        c,
                                        tx -> {
                                            throw new IllegalStateException("原始业务失败");
                                        }));
        assertEquals("原始业务失败", primary.getMessage());
        assertEquals(1, primary.getSuppressed().length);
        assertEquals(
                java.util.List.of("auto=false", "close"), events, "回滚失败后禁止setAutoCommit(true)");
    }
}
