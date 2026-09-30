import static org.junit.jupiter.api.Assertions.*;

import labs.BoundedBuffers;

import org.junit.jupiter.api.*;

import java.util.*;
import java.util.concurrent.*;
import java.util.function.IntFunction;

@Timeout(12)
class BoundedBuffersTest {
    final List<IntFunction<BoundedBuffers.Buffer<Integer>>> factories =
            List.of(BoundedBuffers.MonitorBuffer::new, BoundedBuffers.LockBuffer::new);

    @Test
    void fifoCloseAndValidation() throws Exception {
        for (var factory : factories) {
            assertThrows(IllegalArgumentException.class, () -> factory.apply(0));
            var b = factory.apply(2);
            assertThrows(NullPointerException.class, () -> b.put(null));
            b.put(1);
            b.put(2);
            assertEquals(2, b.size());
            b.close();
            b.close();
            assertEquals(Optional.of(1), b.take());
            assertEquals(Optional.of(2), b.take());
            assertEquals(Optional.empty(), b.take());
            assertThrows(IllegalStateException.class, () -> b.put(3));
            assertEquals(0, b.size());
        }
    }

    @Test
    void closingWakesConsumersAndProducers() throws Exception {
        for (var factory : factories) {
            var empty = factory.apply(1);
            var full = factory.apply(1);
            full.put(1);
            var entered = new CountDownLatch(4);
            try (var pool = Executors.newFixedThreadPool(4)) {
                var consumers = new ArrayList<Future<Optional<Integer>>>();
                var producers = new ArrayList<Future<Boolean>>();
                for (int i = 0; i < 2; i++)
                    consumers.add(
                            pool.submit(
                                    () -> {
                                        entered.countDown();
                                        return empty.take();
                                    }));
                for (int i = 0; i < 2; i++)
                    producers.add(
                            pool.submit(
                                    () -> {
                                        entered.countDown();
                                        try {
                                            full.put(2);
                                            return false;
                                        } catch (IllegalStateException expected) {
                                            return true;
                                        }
                                    }));
                try {
                    assertTrue(entered.await(2, TimeUnit.SECONDS));
                    empty.close();
                    full.close();
                    for (var f : consumers)
                        assertEquals(Optional.empty(), f.get(2, TimeUnit.SECONDS));
                    for (var f : producers) assertTrue(f.get(2, TimeUnit.SECONDS));
                } finally {
                    empty.close();
                    full.close();
                    pool.shutdownNow();
                }
            }
        }
    }

    @Test
    void producersAndConsumerPreserveAllElements() throws Exception {
        for (var factory : factories) {
            var b = factory.apply(2);
            var start = new CountDownLatch(1);
            try (var pool = Executors.newFixedThreadPool(3)) {
                var first =
                        pool.submit(
                                () -> {
                                    start.await();
                                    for (int i = 0; i < 40; i++) b.put(i);
                                    return null;
                                });
                var second =
                        pool.submit(
                                () -> {
                                    start.await();
                                    for (int i = 40; i < 80; i++) b.put(i);
                                    return null;
                                });
                var consumer =
                        pool.submit(
                                () -> {
                                    start.await();
                                    var seen = new HashSet<Integer>();
                                    Optional<Integer> x;
                                    while ((x = b.take()).isPresent())
                                        assertTrue(seen.add(x.get()), "不能重复消费");
                                    return seen;
                                });
                try {
                    start.countDown();
                    first.get(3, TimeUnit.SECONDS);
                    second.get(3, TimeUnit.SECONDS);
                    b.close();
                    assertEquals(80, consumer.get(3, TimeUnit.SECONDS).size());
                } finally {
                    b.close();
                    pool.shutdownNow();
                }
            }
        }
    }

    @Test
    void interruptedWaiterDoesNotPoisonLock() throws Exception {
        for (var factory : factories) {
            var b = factory.apply(1);
            var entered = new CountDownLatch(1);
            var interrupted = new CountDownLatch(1);
            Thread waiter =
                    Thread.ofPlatform()
                            .daemon()
                            .start(
                                    () -> {
                                        entered.countDown();
                                        try {
                                            b.take();
                                        } catch (InterruptedException expected) {
                                            interrupted.countDown();
                                        }
                                    });
            try {
                assertTrue(entered.await(2, TimeUnit.SECONDS));
                waiter.interrupt();
                assertTrue(interrupted.await(2, TimeUnit.SECONDS));
                b.put(7);
                assertEquals(Optional.of(7), b.take());
            } finally {
                b.close();
                waiter.interrupt();
                waiter.join(2000);
                assertFalse(waiter.isAlive());
            }
        }
    }
}
