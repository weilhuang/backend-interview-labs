import static org.junit.jupiter.api.Assertions.*;

import labs.*;

import org.junit.jupiter.api.*;

import java.sql.*;
import java.util.*;

@Tag("integration")
class StockDatabaseTest {
    @BeforeEach
    void reset() throws Exception {
        MySqlFixture.reset();
    }

    @Test
    void contentionDoesNotOversell() throws Exception {
        try (var pool = java.util.concurrent.Executors.newFixedThreadPool(6)) {
            var jobs = new ArrayList<java.util.concurrent.Future<StockLab.Result>>();
            for (int i = 0; i < 30; i++) {
                final int id = i;
                jobs.add(pool.submit(() -> StockLab.reserve(MySqlFixture::open, "r" + id, 101, 1)));
            }
            int accepted = 0;
            for (var job : jobs)
                if (job.get(15, java.util.concurrent.TimeUnit.SECONDS) == StockLab.Result.APPLIED)
                    accepted++;
            assertEquals(10, accepted);
        }
        try (Connection c = MySqlFixture.open()) {
            assertEquals(0, Db.scalar(c, "SELECT quantity FROM c06_stock WHERE sku=101"));
            assertEquals(10, Db.scalar(c, "SELECT COUNT(*) FROM c06_reservation"));
        }
    }

    @Test
    void parallelSameRequestAppliedOnceAndConflictsRejected() throws Exception {
        // 先证明单请求真正提交扣减；未实现时直接暴露 TODO，避免并发回滚的死锁掩盖它。
        assertEquals(
                StockLab.Result.APPLIED, StockLab.reserve(MySqlFixture::open, "single", 101, 2));
        try (Connection c = MySqlFixture.open()) {
            assertEquals(8, Db.scalar(c, "SELECT quantity FROM c06_stock WHERE sku=101"));
            assertEquals(1, Db.scalar(c, "SELECT version FROM c06_stock WHERE sku=101"));
            assertEquals(1, Db.scalar(c, "SELECT COUNT(*) FROM c06_reservation"));
            assertEquals(
                    1,
                    Db.scalar(
                            c,
                            "SELECT COUNT(*) FROM c06_reservation WHERE request_id='single'"
                                    + " AND sku=101 AND quantity=2"));
        }
        // 恢复原始空去重表和库存 10，再从零竞争；不能预先插入 same 让并发退化为重放。
        MySqlFixture.reset();
        try (var pool = java.util.concurrent.Executors.newFixedThreadPool(4)) {
            var jobs = new ArrayList<java.util.concurrent.Future<StockLab.Result>>();
            for (int i = 0; i < 8; i++)
                jobs.add(pool.submit(() -> StockLab.reserve(MySqlFixture::open, "same", 101, 1)));
            int accepted = 0;
            for (var job : jobs) {
                var result = job.get(15, java.util.concurrent.TimeUnit.SECONDS);
                if (result == StockLab.Result.APPLIED) accepted++;
                else assertEquals(StockLab.Result.REPLAY, result);
            }
            assertEquals(1, accepted);
        }
        assertThrows(
                IllegalArgumentException.class,
                () -> StockLab.reserve(MySqlFixture::open, "same", 102, 2));
        try (Connection c = MySqlFixture.open()) {
            assertEquals(9, Db.scalar(c, "SELECT quantity FROM c06_stock WHERE sku=101"));
            assertEquals(1, Db.scalar(c, "SELECT version FROM c06_stock WHERE sku=101"));
            assertEquals(1, Db.scalar(c, "SELECT COUNT(*) FROM c06_reservation"));
        }
    }

    @Test
    void staleVersionAndSoldOutDoNotLeaveDedupeRows() throws Exception {
        try (Connection c = MySqlFixture.open()) {
            assertTrue(StockLab.optimistic(c, 101, 0, 1));
            assertFalse(StockLab.optimistic(c, 101, 0, 1));
        }
        assertEquals(
                StockLab.Result.SOLD_OUT,
                StockLab.reserve(MySqlFixture::open, "too-many", 101, 20));
        try (Connection c = MySqlFixture.open()) {
            assertEquals(
                    0,
                    Db.scalar(
                            c, "SELECT COUNT(*) FROM c06_reservation WHERE request_id='too-many'"));
            assertEquals(9, Db.scalar(c, "SELECT quantity FROM c06_stock WHERE sku=101"));
        }
    }

    @Test
    void gateClosesConnectionEvenWhenWorkFails() throws Exception {
        var gate = new StockLab.Gate(1);
        Connection c = MySqlFixture.open();
        assertThrows(
                SQLException.class,
                () ->
                        gate.run(
                                () -> c,
                                conn -> {
                                    throw new SQLException("业务故障");
                                }));
        assertTrue(c.isClosed());
        assertEquals(1, gate.available());
    }

    @Test
    void requestIdentifiersUseCaseSensitiveNoPadCollation() throws Exception {
        assertEquals(StockLab.Result.APPLIED, StockLab.reserve(MySqlFixture::open, "Case", 101, 1));
        assertEquals(StockLab.Result.APPLIED, StockLab.reserve(MySqlFixture::open, "case", 101, 1));
        assertEquals(
                StockLab.Result.APPLIED, StockLab.reserve(MySqlFixture::open, "case ", 101, 1));
        assertEquals(StockLab.Result.REPLAY, StockLab.reserve(MySqlFixture::open, "Case", 101, 1));
        try (Connection c = MySqlFixture.open()) {
            assertEquals(7, Db.scalar(c, "SELECT quantity FROM c06_stock WHERE sku=101"));
        }
    }
}
