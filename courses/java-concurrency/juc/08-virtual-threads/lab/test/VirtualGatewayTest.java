import static org.junit.jupiter.api.Assertions.*;

import labs.VirtualGateway;

import org.junit.jupiter.api.*;

import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;

@Timeout(12)
class VirtualGatewayTest {
    @Test
    void virtualThreadsStillHonorDownstreamBound() throws Exception {
        var ready = new CountDownLatch(2);
        var release = new CountDownLatch(1);
        var running = new AtomicInteger();
        var maximum = new AtomicInteger();
        try (var gateway = new VirtualGateway(2, 6)) {
            var tasks = new ArrayList<Future<Integer>>();
            try {
                for (int i = 0; i < 6; i++) {
                    final int id = i;
                    tasks.add(
                            gateway.submit(
                                    () -> {
                                        assertTrue(Thread.currentThread().isVirtual());
                                        int active = running.incrementAndGet();
                                        maximum.accumulateAndGet(active, Math::max);
                                        ready.countDown();
                                        try {
                                            release.await();
                                            return id;
                                        } finally {
                                            running.decrementAndGet();
                                        }
                                    }));
                }
                assertTrue(ready.await(2, TimeUnit.SECONDS));
                assertEquals(0, gateway.availableDownstream());
                assertThrows(RejectedExecutionException.class, () -> gateway.submit(() -> 7));
                release.countDown();
                int sum = 0;
                for (var task : tasks) sum += task.get(3, TimeUnit.SECONDS);
                assertEquals(15, sum);
                assertEquals(2, maximum.get());
                assertEquals(2, gateway.availableDownstream());
            } finally {
                release.countDown();
            }
        }
    }

    @Test
    void cancellationAndExceptionReturnPermits() throws Exception {
        var started = new CountDownLatch(1);
        var release = new CountDownLatch(1);
        var cleaned = new CountDownLatch(1);
        try (var gateway = new VirtualGateway(1, 3)) {
            var running =
                    gateway.submit(
                            () -> {
                                started.countDown();
                                try {
                                    release.await();
                                    return 1;
                                } finally {
                                    cleaned.countDown();
                                }
                            });
            try {
                assertTrue(started.await(2, TimeUnit.SECONDS));
                var waiting = gateway.submit(() -> 2);
                assertTrue(waiting.cancel(true));
                assertTrue(running.cancel(true));
                assertTrue(cleaned.await(2, TimeUnit.SECONDS));
                var next =
                        gateway.submit(
                                () -> {
                                    throw new IllegalStateException("业务故障");
                                });
                assertInstanceOf(
                        IllegalStateException.class,
                        assertThrows(ExecutionException.class, () -> next.get(2, TimeUnit.SECONDS))
                                .getCause());
                var finalTask = gateway.submit(() -> 3);
                assertEquals(3, finalTask.get(2, TimeUnit.SECONDS));
                assertEquals(1, gateway.availableDownstream());
            } finally {
                release.countDown();
            }
        }
    }

    @Test
    void cancelledFutureDoesNotReleaseAdmissionUntilActionActuallyExits() throws Exception {
        var entered = new CountDownLatch(1);
        var sawInterrupt = new CountDownLatch(1);
        var release = new CountDownLatch(1);
        try (var gateway = new VirtualGateway(1, 1)) {
            var future =
                    gateway.submit(
                            () -> {
                                entered.countDown();
                                try {
                                    release.await();
                                } catch (InterruptedException cancelled) {
                                    sawInterrupt.countDown();
                                    release.await();
                                }
                                return 1;
                            });
            try {
                assertTrue(entered.await(2, TimeUnit.SECONDS));
                assertTrue(future.cancel(true));
                assertTrue(sawInterrupt.await(2, TimeUnit.SECONDS));
                assertTrue(future.isDone());
                assertEquals(0, gateway.availableDownstream());
                assertThrows(
                        RejectedExecutionException.class,
                        () -> gateway.submit(() -> 2),
                        "Future取消不能提前释放实际受理容量");
            } finally {
                release.countDown();
            }
        }
    }

    @Test
    void closeRejectsNewWork() throws Exception {
        var gateway = new VirtualGateway(1, 1);
        gateway.close();
        assertThrows(RejectedExecutionException.class, () -> gateway.submit(() -> 1));
    }

    @Test
    void boundsPreventAccidentalLargeLoad() {
        assertThrows(IllegalArgumentException.class, () -> new VirtualGateway(0, 1));
        assertThrows(IllegalArgumentException.class, () -> new VirtualGateway(17, 20));
        assertThrows(IllegalArgumentException.class, () -> new VirtualGateway(1, 65));
    }
}
