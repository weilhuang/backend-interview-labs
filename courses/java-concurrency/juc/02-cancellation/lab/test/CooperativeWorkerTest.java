import static org.junit.jupiter.api.Assertions.*;

import labs.CooperativeWorker;

import org.junit.jupiter.api.*;

import java.time.Duration;
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;

@Timeout(10)
class CooperativeWorkerTest {
    @Test
    void interruptClosesResourceExactlyOnce() throws Exception {
        var inside = new CountDownLatch(1);
        var block = new CountDownLatch(1);
        var cleaned = new AtomicInteger();
        var worker =
                new CooperativeWorker(
                        () -> {
                            inside.countDown();
                            block.await();
                        },
                        cleaned::incrementAndGet);
        worker.start();
        try {
            assertTrue(inside.await(2, TimeUnit.SECONDS));
            assertTrue(worker.cancelAndAwait(Duration.ofSeconds(2)));
            assertEquals(1, cleaned.get());
            assertNull(worker.failure());
        } finally {
            block.countDown();
            worker.cancelAndAwait(Duration.ofSeconds(2));
        }
    }

    @Test
    void ignoredSignalCannotBeReportedAsStopped() throws Exception {
        var entered = new CountDownLatch(1);
        var interrupted = new CountDownLatch(1);
        var release = new CountDownLatch(1);
        var worker =
                new CooperativeWorker(
                        () -> {
                            entered.countDown();
                            try {
                                new CountDownLatch(1).await();
                            } catch (InterruptedException expected) {
                                interrupted.countDown();
                                release.await();
                            }
                        },
                        () -> {});
        worker.start();
        try {
            assertTrue(entered.await(2, TimeUnit.SECONDS));
            assertFalse(worker.cancelAndAwait(Duration.ZERO));
            assertTrue(interrupted.await(2, TimeUnit.SECONDS));
            assertTrue(worker.alive());
        } finally {
            release.countDown();
            assertTrue(worker.awaitStopped(Duration.ofSeconds(2)));
        }
    }

    @Test
    void failuresAreVisibleAndCleanupStillRuns() throws Exception {
        var cleaned = new AtomicBoolean();
        var expected = new IllegalStateException("模拟业务错误");
        var worker =
                new CooperativeWorker(
                        () -> {
                            throw expected;
                        },
                        () -> cleaned.set(true));
        worker.start();
        assertTrue(worker.awaitStopped(Duration.ofSeconds(2)));
        assertSame(expected, worker.failure());
        assertTrue(cleaned.get());
    }

    @Test
    void budgetValidationPrecedesSignal() {
        var worker = new CooperativeWorker(() -> {}, () -> {});
        assertThrows(
                IllegalArgumentException.class,
                () -> worker.cancelAndAwait(Duration.ofSeconds(-1)));
        assertThrows(NullPointerException.class, () -> worker.cancelAndAwait(null));
    }

    @Test
    void startupAndDuplicateStartAreExplicit() throws Exception {
        var worker = new CooperativeWorker(() -> {}, () -> {});
        worker.start();
        assertTrue(worker.awaitStarted(Duration.ofSeconds(2)));
        assertThrows(IllegalThreadStateException.class, worker::start);
        assertTrue(worker.awaitStopped(Duration.ofSeconds(2)));
    }
}
