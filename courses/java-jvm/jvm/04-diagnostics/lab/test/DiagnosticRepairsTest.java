import static org.junit.jupiter.api.Assertions.*;

import labs.jvm.*;

import org.junit.jupiter.api.*;

import java.util.concurrent.*;

@Timeout(8)
class DiagnosticRepairsTest {
    @Test
    void cpuHasFiniteWorkBudget() {
        assertEquals(49995000, DiagnosticRepairs.finiteChecksum(10000));
        assertThrows(
                IllegalArgumentException.class, () -> DiagnosticRepairs.finiteChecksum(1000001));
    }

    @Test
    void retentionCannotGrowWithTotalRequests() {
        assertEquals(3, DiagnosticRepairs.boundedRetention(64, 3));
        assertEquals(0, DiagnosticRepairs.boundedRetention(0, 3));
    }

    @Test
    void blockingWorkIsOutsideMonitor() throws Exception {
        var c = new DiagnosticRepairs.Counter();
        var entered = new CountDownLatch(1);
        var release = new CountDownLatch(1);
        var pool = Executors.newFixedThreadPool(2);
        try {
            var blocked =
                    pool.submit(
                            () ->
                                    c.incrementAfter(
                                            () -> {
                                                entered.countDown();
                                                release.await();
                                                return null;
                                            }));
            assertTrue(entered.await(2, TimeUnit.SECONDS));
            assertEquals(
                    1,
                    pool.submit(() -> c.incrementAfter(() -> null)).get(2, TimeUnit.SECONDS),
                    "慢操作不能持有计数器监视器");
            release.countDown();
            assertEquals(2, blocked.get(2, TimeUnit.SECONDS));
            assertEquals(2, c.value());
        } finally {
            release.countDown();
            pool.shutdownNow();
            assertTrue(pool.awaitTermination(2, TimeUnit.SECONDS));
        }
    }

    @Test
    void saturatedPoolRejectsAndCloses() throws Exception {
        var release = new CountDownLatch(1);
        var entered = new CountDownLatch(1);
        var pool = new ThreadPoolExecutor(1, 1, 0, TimeUnit.SECONDS, new ArrayBlockingQueue<>(1));
        try {
            pool.execute(
                    () -> {
                        entered.countDown();
                        try {
                            release.await();
                        } catch (InterruptedException e) {
                            Thread.currentThread().interrupt();
                        }
                    });
            assertTrue(entered.await(2, TimeUnit.SECONDS));
            pool.execute(() -> {});
            assertThrows(RejectedExecutionException.class, () -> pool.execute(() -> {}));
            release.countDown();
            assertTrue(DiagnosticRepairs.closePool(pool));
            assertTrue(pool.isTerminated());
        } finally {
            release.countDown();
            pool.shutdownNow();
            pool.awaitTermination(2, TimeUnit.SECONDS);
        }
    }
}
