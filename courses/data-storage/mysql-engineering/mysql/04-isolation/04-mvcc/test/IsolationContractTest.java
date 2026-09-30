import static org.junit.jupiter.api.Assertions.*;

import labs.*;

import org.junit.jupiter.api.*;

import java.sql.*;
import java.util.*;

class IsolationContractTest {
    @Test
    void expectedScenariosExplicitlyLimited() {
        assertEquals(10, IsolationLab.expectedSecond(Connection.TRANSACTION_REPEATABLE_READ));
        assertEquals(11, IsolationLab.expectedSecond(Connection.TRANSACTION_READ_COMMITTED));
        assertThrows(
                IllegalArgumentException.class,
                () -> IsolationLab.expectedSecond(Connection.TRANSACTION_SERIALIZABLE));
    }

    @Test
    void rollbackFailureDiscardsConnectionWithoutTurningOnAutocommit() throws Exception {
        var events = new java.util.ArrayList<String>();
        Connection reader =
                (Connection)
                        java.lang.reflect.Proxy.newProxyInstance(
                                getClass().getClassLoader(),
                                new Class[] {Connection.class},
                                (proxy, method, args) ->
                                        switch (method.getName()) {
                                            case "getAutoCommit" -> true;
                                            case "getTransactionIsolation" ->
                                                    Connection.TRANSACTION_REPEATABLE_READ;
                                            case "setTransactionIsolation" -> null;
                                            case "setAutoCommit" -> {
                                                events.add("auto=" + args[0]);
                                                yield null;
                                            }
                                            case "prepareStatement" ->
                                                    throw new SQLException("读取失败");
                                            case "rollback" -> throw new SQLException("回滚失败");
                                            case "close" -> {
                                                events.add("close");
                                                yield null;
                                            }
                                            default ->
                                                    throw new UnsupportedOperationException(
                                                            method.getName());
                                        });
        SQLException failure =
                assertThrows(
                        SQLException.class,
                        () ->
                                IsolationLab.observe(
                                        reader, reader, Connection.TRANSACTION_REPEATABLE_READ));
        assertEquals("读取失败", failure.getMessage());
        assertEquals(1, failure.getSuppressed().length);
        assertEquals(java.util.List.of("auto=false", "close"), events);
    }
}
