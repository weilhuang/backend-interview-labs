import static org.junit.jupiter.api.Assertions.*;

import labs.*;

import org.junit.jupiter.api.*;

import java.sql.*;

@Tag("integration")
class PoolDatabaseTest {
    @BeforeEach
    void reset() throws Exception {
        MySqlFixture.reset();
    }

    @Test
    void capacityExhaustionIsBoundedAndBorrowWorksAfterReturn() throws Exception {
        var mysql = MySqlFixture.MYSQL;
        try (var pool =
                PoolLab.create(mysql.getJdbcUrl(), mysql.getUsername(), mysql.getPassword(), 1)) {
            try (Connection held = pool.getConnection()) {
                assertEquals(1, Db.scalar(held, "SELECT 1"));
                assertThrows(SQLTransientConnectionException.class, pool::getConnection);
                assertEquals(1, pool.getHikariPoolMXBean().getActiveConnections());
            }
            try (Connection recovered = pool.getConnection()) {
                assertEquals(1, Db.scalar(recovered, "SELECT 1"));
            }
            assertEquals(0, pool.getHikariPoolMXBean().getActiveConnections());
        }
    }

    @Test
    void closeRollsBackUncommittedWorkAndResetsSession() throws Exception {
        var mysql = MySqlFixture.MYSQL;
        try (var pool =
                PoolLab.create(mysql.getJdbcUrl(), mysql.getUsername(), mysql.getPassword(), 1)) {
            try (Connection c = pool.getConnection()) {
                c.setAutoCommit(false);
                Db.update(c, "UPDATE c06_stock SET quantity=1 WHERE sku=101");
            }
            try (Connection c = pool.getConnection()) {
                assertTrue(c.getAutoCommit());
                assertEquals(10, Db.scalar(c, "SELECT quantity FROM c06_stock WHERE sku=101"));
            }
        }
    }
}
