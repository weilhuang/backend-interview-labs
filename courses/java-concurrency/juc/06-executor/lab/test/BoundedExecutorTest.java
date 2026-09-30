import static org.junit.jupiter.api.Assertions.*;

import labs.BoundedExecutor;

import org.junit.jupiter.api.*;

import java.time.Duration;
import java.util.concurrent.*;

@Timeout(10)
class BoundedExecutorTest {
    @Test
    void coreThenQueueThenMaxThenReject() throws Exception {
        var pool = new BoundedExecutor(1, 2, 1);
        var coreStarted = new CountDownLatch(1);
        var maxStarted = new CountDownLatch(1);
        var release = new CountDownLatch(1);
        try {
            var one =
                    pool.submit(
                            () -> {
                                coreStarted.countDown();
                                release.await();
                                return 1;
                            });
            assertTrue(coreStarted.await(2, TimeUnit.SECONDS));
            var two = pool.submit(() -> 2);
            assertEquals(1, pool.queued());
            var three =
                    pool.submit(
                            () -> {
                                maxStarted.countDown();
                                release.await();
                                return 3;
                            });
            assertTrue(maxStarted.await(2, TimeUnit.SECONDS));
            assertEquals(2, pool.workers());
            assertThrows(
                    RejectedExecutionException.class, () -> pool.submit(() -> 4), "必须显式拒绝，不能静默丢弃");
            release.countDown();
            assertEquals(1, one.get(2, TimeUnit.SECONDS));
            assertEquals(2, two.get(2, TimeUnit.SECONDS));
            assertEquals(3, three.get(2, TimeUnit.SECONDS));
        } finally {
            release.countDown();
            pool.shutdown(Duration.ofSeconds(2));
            assertTrue(pool.awaitStopped(Duration.ofSeconds(2)));
        }
    }

    @Test
    void cancelledQueueSlotIsReusable() throws Exception {
        var pool = new BoundedExecutor(1, 1, 1);
        var entered = new CountDownLatch(1);
        var release = new CountDownLatch(1);
        try {
            var running =
                    pool.submit(
                            () -> {
                                entered.countDown();
                                release.await();
                                return 0;
                            });
            assertTrue(entered.await(2, TimeUnit.SECONDS));
            var queued = pool.submit(() -> 1);
            assertTrue(pool.cancelQueued(queued));
            assertTrue(queued.isCancelled());
            assertEquals(0, pool.queued());
            var replacement = pool.submit(() -> 2);
            release.countDown();
            assertEquals(0, running.get(2, TimeUnit.SECONDS));
            assertEquals(2, replacement.get(2, TimeUnit.SECONDS));
        } finally {
            release.countDown();
            pool.shutdown(Duration.ofSeconds(2));
            assertTrue(pool.awaitStopped(Duration.ofSeconds(2)));
        }
    }

    @Test
    void taskFailureIsObservedThroughFuture() throws Exception {
        var pool = new BoundedExecutor(1, 1, 1);
        try {
            var f =
                    pool.submit(
                            () -> {
                                throw new IllegalStateException("业务失败");
                            });
            var e = assertThrows(ExecutionException.class, () -> f.get(2, TimeUnit.SECONDS));
            assertInstanceOf(IllegalStateException.class, e.getCause());
        } finally {
            pool.shutdown(Duration.ofSeconds(2));
            assertTrue(pool.awaitStopped(Duration.ofSeconds(2)));
        }
    }

    @Test
    void forcedShutdownCompletesAbandonedFutures() throws Exception {
        var pool = new BoundedExecutor(1, 1, 1);
        var entered = new CountDownLatch(1);
        var release = new CountDownLatch(1);
        try {
            pool.submit(
                    () -> {
                        entered.countDown();
                        release.await();
                        return 1;
                    });
            assertTrue(entered.await(2, TimeUnit.SECONDS));
            var queued = pool.submit(() -> 2);
            pool.shutdown(Duration.ZERO);
            assertTrue(queued.isCancelled(), "shutdownNow取出的Future也要结束");
            assertThrows(RejectedExecutionException.class, () -> pool.submit(() -> 3));
            assertTrue(pool.awaitStopped(Duration.ofSeconds(2)));
        } finally {
            release.countDown();
            pool.shutdown(Duration.ofSeconds(2));
        }
    }

    @Test
    void parameters() {
        assertThrows(IllegalArgumentException.class, () -> new BoundedExecutor(2, 1, 1));
        assertThrows(IllegalArgumentException.class, () -> new BoundedExecutor(1, 1, 0));
    }
}
