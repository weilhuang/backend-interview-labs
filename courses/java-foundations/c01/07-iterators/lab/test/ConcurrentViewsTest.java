import static org.junit.jupiter.api.Assertions.*;

import labs.foundation.*;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.Timeout;

import java.util.*;
import java.util.concurrent.*;

@Timeout(8)
class ConcurrentViewsTest {
    @Test
    void safeRemovalAndNull() {
        var values = new ArrayList<>(List.of(-1, 2, -3, 0, -4));
        assertEquals(3, ConcurrentViews.removeNegatives(values));
        assertEquals(List.of(2, 0), values);
        assertEquals(0, ConcurrentViews.removeNegatives(values));
        assertThrows(
                NullPointerException.class,
                () ->
                        ConcurrentViews.removeNegatives(
                                new ArrayList<>(Arrays.asList((Integer) null))));
    }

    @Test
    void snapshotsAndWeakConsistency() {
        var cow = new CopyOnWriteArrayList<>(List.of("旧"));
        var snapshot = cow.iterator();
        cow.add("新");
        assertEquals(List.of("旧"), ConcurrentViews.collect(snapshot));
        assertThrows(
                UnsupportedOperationException.class,
                () -> {
                    var iterator = cow.iterator();
                    iterator.next();
                    iterator.remove();
                });
        var map = new ConcurrentHashMap<String, Integer>();
        map.put("稳定", 1);
        var iterator = map.keySet().iterator();
        map.put("新增", 2);
        var observed = ConcurrentViews.collect(iterator);
        assertTrue(Set.of("稳定", "新增").containsAll(observed));
        assertEquals(2, map.size());
    }

    @Test
    void atomicComputeAndOverflow() throws Exception {
        var counters = new ConcurrentHashMap<String, Long>();
        var pool = Executors.newFixedThreadPool(4);
        var start = new CountDownLatch(1);
        List<Future<?>> futures = new ArrayList<>();
        try {
            for (int t = 0; t < 4; t++)
                futures.add(
                        pool.submit(
                                () -> {
                                    try {
                                        start.await();
                                        for (int i = 0; i < 200; i++)
                                            ConcurrentViews.increment(counters, "订单");
                                    } catch (InterruptedException e) {
                                        Thread.currentThread().interrupt();
                                    }
                                }));
            start.countDown();
            for (var f : futures) f.get(3, TimeUnit.SECONDS);
            assertEquals(800L, counters.get("订单"));
        } finally {
            start.countDown();
            pool.shutdownNow();
            assertTrue(pool.awaitTermination(2, TimeUnit.SECONDS));
        }
        counters.put("溢出", Long.MAX_VALUE);
        assertThrows(ArithmeticException.class, () -> ConcurrentViews.increment(counters, "溢出"));
        assertEquals(Long.MAX_VALUE, counters.get("溢出"));
    }
}
