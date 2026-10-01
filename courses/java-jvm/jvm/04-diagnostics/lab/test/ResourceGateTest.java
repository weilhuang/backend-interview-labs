import static org.junit.jupiter.api.Assertions.*;

import labs.jvm.*;

import org.junit.jupiter.api.*;

@Timeout(8)
class ResourceGateTest {
    @Test
    void failureReleasesResource() throws Exception {
        var gate = new ResourceGate(1);
        assertThrows(
                IllegalStateException.class,
                () ->
                        gate.call(
                                () -> {
                                    throw new IllegalStateException("业务失败");
                                }));
        assertEquals(1, gate.available(), "异常后必须归还许可");
        assertEquals(0, gate.active());
        assertEquals(7, gate.call(() -> 7));
    }

    @Test
    void boundedConcurrencyAndCancellation() throws Exception {
        var gate = new ResourceGate(1);
        var entered = new java.util.concurrent.CountDownLatch(1);
        var release = new java.util.concurrent.CountDownLatch(1);
        var pool = java.util.concurrent.Executors.newFixedThreadPool(2);
        try {
            var first =
                    pool.submit(
                            () ->
                                    gate.call(
                                            () -> {
                                                entered.countDown();
                                                release.await();
                                                return 1;
                                            }));
            assertTrue(entered.await(2, java.util.concurrent.TimeUnit.SECONDS));
            var attempted = new java.util.concurrent.CountDownLatch(1);
            var second =
                    pool.submit(
                            () -> {
                                attempted.countDown();
                                return gate.call(() -> 2);
                            });
            assertTrue(attempted.await(2, java.util.concurrent.TimeUnit.SECONDS));
            second.cancel(true);
            assertEquals(1, gate.active());
            assertEquals(0, gate.available(), "被中断的等待者不能凭空增加许可");
            release.countDown();
            assertEquals(1, first.get(2, java.util.concurrent.TimeUnit.SECONDS));
        } finally {
            release.countDown();
            pool.shutdownNow();
            assertTrue(pool.awaitTermination(2, java.util.concurrent.TimeUnit.SECONDS));
        }
        assertEquals(1, gate.peak());
        assertEquals(1, gate.available());
        assertEquals(0, gate.active());
    }

    @Test
    void invalid() {
        assertThrows(IllegalArgumentException.class, () -> new ResourceGate(0));
        assertThrows(IllegalArgumentException.class, () -> new ResourceGate(9));
    }
}
