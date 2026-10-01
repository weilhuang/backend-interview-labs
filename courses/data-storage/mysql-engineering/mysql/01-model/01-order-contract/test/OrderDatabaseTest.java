import static org.junit.jupiter.api.Assertions.*;

import labs.*;

import org.junit.jupiter.api.*;

import java.sql.*;
import java.util.*;

@Tag("integration")
class OrderDatabaseTest {
    @BeforeEach
    void reset() throws Exception {
        MySqlFixture.reset();
    }

    @Test
    void aggregationAndTenantBoundary() throws Exception {
        try (Connection c = MySqlFixture.open()) {
            assertEquals(3500, OrderQueries.paidTotal(c, 7));
            assertEquals(500, OrderQueries.paidTotal(c, 8));
            assertEquals(0, OrderQueries.paidTotal(c, 404));
            assertEquals(Map.of(101L, 2L, 102L, 3L), OrderQueries.quantities(c, 7));
        }
    }

    @Test
    void constraintsRejectCorruptRows() throws Exception {
        try (Connection c = MySqlFixture.open()) {
            assertThrows(
                    SQLException.class,
                    () ->
                            Db.update(
                                    c,
                                    "INSERT INTO c06_orders SELECT"
                                        + " 9,tenant_id,request_id,customer_id,status,total_cents,created_at"
                                        + " FROM c06_orders WHERE id=1"));
            assertThrows(
                    SQLException.class,
                    () -> Db.update(c, "INSERT INTO c06_item VALUES(999,101,1,10)"));
            assertThrows(
                    SQLException.class,
                    () -> Db.update(c, "UPDATE c06_stock SET quantity=-1 WHERE sku=101"));
            assertEquals(4, Db.scalar(c, "SELECT COUNT(*) FROM c06_orders"));
        }
    }

    @Test
    void joinsDoNotMultiplyOrderMoney() throws Exception {
        try (Connection c = MySqlFixture.open()) {
            assertEquals(
                    5000,
                    Db.scalar(
                            c,
                            "SELECT SUM(o.total_cents) FROM c06_orders o JOIN c06_item i ON"
                                + " i.order_id=o.id WHERE o.tenant_id=7 AND o.status='PAID'"));
            assertEquals(3500, OrderQueries.paidTotal(c, 7));
        }
    }

    @Test
    void runtimeFailureRollsBackAndRestoresConnection() throws Exception {
        try (Connection c = MySqlFixture.open()) {
            assertThrows(
                    IllegalStateException.class,
                    () ->
                            Db.transaction(
                                    c,
                                    tx -> {
                                        Db.update(tx, "DELETE FROM c06_item");
                                        throw new IllegalStateException("注入故障");
                                    }));
            assertEquals(5, Db.scalar(c, "SELECT COUNT(*) FROM c06_item"));
            assertTrue(c.getAutoCommit());
        }
    }
}
