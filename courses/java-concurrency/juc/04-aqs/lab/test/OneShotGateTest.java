import static org.junit.jupiter.api.Assertions.*;

import labs.OneShotGate;

import org.junit.jupiter.api.*;

import java.time.Duration;
import java.util.*;
import java.util.concurrent.*;

@Timeout(10)
class OneShotGateTest {
    @Test
    void closedOpenIdempotentAndZeroBudget() throws Exception {
        var gate = new OneShotGate();
        assertFalse(gate.isOpen());
        assertFalse(gate.await(Duration.ZERO));
        gate.open();
        gate.open();
        assertTrue(gate.isOpen());
        assertTrue(gate.await(Duration.ZERO));
        assertThrows(IllegalArgumentException.class, () -> gate.await(Duration.ofSeconds(-1)));
        assertThrows(NullPointerException.class, () -> gate.await(null));
    }

    @Test
    void openReleasesEveryWaiterAndPublishesData() throws Exception {
        var gate = new OneShotGate();
        var ready = new CountDownLatch(4);
        int[] data = {0};
        try (var pool = Executors.newFixedThreadPool(4)) {
            var pending = new ArrayList<Future<Integer>>();
            for (int i = 0; i < 4; i++)
                pending.add(
                        pool.submit(
                                () -> {
                                    ready.countDown();
                                    gate.await();
                                    return data[0];
                                }));
            try {
                assertTrue(ready.await(2, TimeUnit.SECONDS));
                data[0] = 42;
                gate.open();
                for (var f : pending) assertEquals(42, f.get(2, TimeUnit.SECONDS));
            } finally {
                gate.open();
                pool.shutdownNow();
            }
        }
    }

    @Test
    void interruptedWaiterDoesNotConsumeOpen() throws Exception {
        var gate = new OneShotGate();
        var ready = new CountDownLatch(1);
        var cancelled = new CountDownLatch(1);
        Thread waiter =
                Thread.ofPlatform()
                        .daemon()
                        .start(
                                () -> {
                                    ready.countDown();
                                    try {
                                        gate.await();
                                    } catch (InterruptedException expected) {
                                        cancelled.countDown();
                                    }
                                });
        try {
            assertTrue(ready.await(2, TimeUnit.SECONDS));
            waiter.interrupt();
            assertTrue(cancelled.await(2, TimeUnit.SECONDS));
            assertFalse(gate.isOpen());
            gate.open();
            assertTrue(gate.await(Duration.ZERO));
        } finally {
            gate.open();
            waiter.interrupt();
            waiter.join(2000);
            assertFalse(waiter.isAlive());
        }
    }

    @Test
    void permitsAndCompletionCountAreDifferent() throws Exception {
        var permits = new Semaphore(1);
        assertTrue(permits.tryAcquire());
        assertFalse(permits.tryAcquire());
        permits.release();
        assertEquals(1, permits.availablePermits());
        var done = new CountDownLatch(2);
        done.countDown();
        assertFalse(done.await(0, TimeUnit.NANOSECONDS));
        done.countDown();
        assertTrue(done.await(0, TimeUnit.NANOSECONDS));
    }
}
