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
            var pool = Executors.newFixedThreadPool(3);
            var completed = new ExecutorCompletionService<Set<Integer>>(pool);
            var futures = new ArrayList<Future<Set<Integer>>>();
            Throwable primary = null;
            try {
                var first =
                        completed.submit(
                                () -> {
                                    start.await();
                                    for (int i = 0; i < 40; i++) b.put(i);
                                    return null;
                                });
                var second =
                        completed.submit(
                                () -> {
                                    start.await();
                                    for (int i = 40; i < 80; i++) b.put(i);
                                    return null;
                                });
                var consumer =
                        completed.submit(
                                () -> {
                                    start.await();
                                    var seen = new HashSet<Integer>();
                                    Optional<Integer> x;
                                    while ((x = b.take()).isPresent())
                                        assertTrue(seen.add(x.get()), "不能重复消费");
                                    return seen;
                                });
                futures.addAll(List.of(first, second, consumer));
                start.countDown();
                int finishedProducers = 0;
                for (int i = 0; i < futures.size(); i++) {
                    var done = completed.poll(3, TimeUnit.SECONDS);
                    assertNotNull(done, "并发任务未按期限完成，请检查等待条件与通知");
                    // 按完成顺序传播错误：消费者的TODO不能被等待生产者的超时遮住。
                    var values = done.get();
                    if (done == consumer) {
                        assertEquals(80, values.size());
                    } else if (++finishedProducers == 2) {
                        b.close();
                    }
                }
            } catch (Exception | Error failure) {
                primary = failure;
                throw failure;
            } finally {
                Throwable cleanup = null;
                try {
                    b.close();
                } catch (Exception | Error failure) {
                    cleanup = failure;
                }
                try {
                    for (var future : futures) future.cancel(true);
                } catch (Exception | Error failure) {
                    cleanup = combine(cleanup, failure);
                }
                try {
                    pool.shutdownNow();
                    assertTrue(pool.awaitTermination(2, TimeUnit.SECONDS), "并发测试线程未正常结束");
                } catch (InterruptedException failure) {
                    Thread.currentThread().interrupt();
                    cleanup = combine(cleanup, failure);
                } catch (Exception | Error failure) {
                    cleanup = combine(cleanup, failure);
                }
                if (cleanup != null) {
                    if (primary != null) primary.addSuppressed(cleanup);
                    else if (cleanup instanceof Exception failure) throw failure;
                    else throw (Error) cleanup;
                }
            }
        }
    }

    private static Throwable combine(Throwable first, Throwable next) {
        if (first == null) return next;
        first.addSuppressed(next);
        return first;
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
