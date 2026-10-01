import static org.junit.jupiter.api.Assertions.*;

import labs.*;

import org.junit.jupiter.api.*;

import java.sql.*;
import java.util.*;

@Tag("integration")
class IsolationDatabaseTest {
    @BeforeEach
    void reset() throws Exception {
        MySqlFixture.reset();
    }

    @Test
    void repeatableReadSnapshotAndCurrentReadDiffer() throws Exception {
        try (Connection a = MySqlFixture.open();
                Connection b = MySqlFixture.open()) {
            assertEquals(
                    new IsolationLab.Trace(10, 10, 11),
                    IsolationLab.observe(a, b, Connection.TRANSACTION_REPEATABLE_READ));
            assertTrue(a.getAutoCommit());
        }
    }

    @Test
    void readCommittedRefreshesReadView() throws Exception {
        try (Connection a = MySqlFixture.open();
                Connection b = MySqlFixture.open()) {
            assertEquals(
                    new IsolationLab.Trace(10, 11, 11),
                    IsolationLab.observe(a, b, Connection.TRANSACTION_READ_COMMITTED));
        }
    }

    @Test
    void rollbackPreventsDirtyReadAndOwnWriteVisible() throws Exception {
        try (Connection a = MySqlFixture.open();
                Connection b = MySqlFixture.open()) {
            a.setAutoCommit(false);
            try {
                Db.update(a, "UPDATE c06_stock SET quantity=8 WHERE sku=101");
                assertEquals(8, Db.scalar(a, "SELECT quantity FROM c06_stock WHERE sku=101"));
                assertEquals(10, Db.scalar(b, "SELECT quantity FROM c06_stock WHERE sku=101"));
            } finally {
                a.rollback();
            }
            assertEquals(10, Db.scalar(b, "SELECT quantity FROM c06_stock WHERE sku=101"));
        }
    }

    @Test
    void startTransactionDoesNotEstablishViewUntilFirstRead() throws Exception {
        try (Connection a = MySqlFixture.open();
                Connection b = MySqlFixture.open()) {
            a.setTransactionIsolation(Connection.TRANSACTION_REPEATABLE_READ);
            a.setAutoCommit(false);
            Db.update(b, "UPDATE c06_stock SET quantity=12 WHERE sku=101");
            assertEquals(12, Db.scalar(a, "SELECT quantity FROM c06_stock WHERE sku=101"));
            a.rollback();
        }
    }
}
