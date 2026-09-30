import static org.junit.jupiter.api.Assertions.*;

import labs.*;

import org.junit.jupiter.api.*;

import java.sql.*;
import java.util.*;

@Tag("integration")
class LockDatabaseTest {
    @BeforeEach
    void reset() throws Exception {
        MySqlFixture.reset();
    }

    @Test
    void opposingOrderCreatesRealDeadlock() throws Exception {
        try (Connection a = MySqlFixture.open();
                Connection b = MySqlFixture.open();
                var pool = java.util.concurrent.Executors.newFixedThreadPool(2)) {
            a.setAutoCommit(false);
            b.setAutoCommit(false);
            LockLab.lockSku(a, 101);
            LockLab.lockSku(b, 102);
            var barrier = new java.util.concurrent.CyclicBarrier(2);
            java.util.concurrent.Callable<Integer> left = () -> secondLock(a, 102, barrier),
                    right = () -> secondLock(b, 101, barrier);
            var x = pool.submit(left);
            var y = pool.submit(right);
            var codes =
                    List.of(
                            x.get(10, java.util.concurrent.TimeUnit.SECONDS),
                            y.get(10, java.util.concurrent.TimeUnit.SECONDS));
            assertTrue(codes.contains(1213), "至少一个真实死锁受害事务");
            assertTrue(codes.contains(0), "另一个事务应在释放锁后完成");
        }
    }

    private int secondLock(Connection c, long sku, java.util.concurrent.CyclicBarrier barrier)
            throws Exception {
        try {
            barrier.await(3, java.util.concurrent.TimeUnit.SECONDS);
            LockLab.lockSku(c, sku);
            c.commit();
            return 0;
        } catch (SQLException e) {
            c.rollback();
            // 只接受本场景制造出的真实死锁；连接/SQL错误不能冒充死锁证据。
            if (e.getErrorCode() != 1213) throw e;
            assertTrue(LockLab.retryable(e), "真实死锁必须交由学习者策略判定为可重试");
            return e.getErrorCode();
        } finally {
            c.rollback();
        }
    }

    @Test
    void rrRangeBlocksGapInsertButRcDoesNot() throws Exception {
        for (int level :
                new int[] {
                    Connection.TRANSACTION_REPEATABLE_READ, Connection.TRANSACTION_READ_COMMITTED
                }) {
            try (Connection a = MySqlFixture.open();
                    Connection b = MySqlFixture.open()) {
                Db.update(b, "DELETE FROM c06_stock WHERE sku=150");
                Db.update(b, "INSERT IGNORE INTO c06_stock VALUES(200,10,0)");
                a.setTransactionIsolation(level);
                a.setAutoCommit(false);
                try {
                    Db.ids(a, "SELECT sku FROM c06_stock WHERE sku>=101 AND sku<200 FOR UPDATE");
                    if (level == Connection.TRANSACTION_REPEATABLE_READ) {
                        SQLException e =
                                assertThrows(
                                        SQLException.class,
                                        () ->
                                                Db.update(
                                                        b,
                                                        "INSERT INTO c06_stock VALUES(150,1,0)"));
                        if (e.getErrorCode() != 1205) throw e;
                        assertTrue(LockLab.retryable(e), "真实锁等待超时必须被判定为可重试");
                    } else assertEquals(1, Db.update(b, "INSERT INTO c06_stock VALUES(150,1,0)"));
                } finally {
                    a.rollback();
                }
            }
        }
    }

    @Test
    void realDuplicateKeyMustNotBeRetried() throws Exception {
        try (Connection c = MySqlFixture.open()) {
            SQLException duplicate =
                    assertThrows(
                            SQLException.class,
                            () -> Db.update(c, "INSERT INTO c06_stock VALUES(101,1,0)"));
            // reset已植入sku=101；只有真实1062属于这条非重试边界。
            if (duplicate.getErrorCode() != 1062) throw duplicate;
            assertFalse(LockLab.retryable(duplicate), "重复主键不能作为死锁盲目重试");
        }
    }

    @Test
    void orderedTransferConservesInventory() throws Exception {
        LockLab.retry(
                MySqlFixture::open,
                3,
                c -> {
                    LockLab.swapOne(c, 101, 102);
                    return null;
                });
        try (Connection c = MySqlFixture.open()) {
            assertEquals(20, Db.scalar(c, "SELECT SUM(quantity) FROM c06_stock"));
            assertEquals(9, Db.scalar(c, "SELECT quantity FROM c06_stock WHERE sku=101"));
        }
    }
}
