import static org.junit.jupiter.api.Assertions.*;

import labs.AtomicLedger;

import org.junit.jupiter.api.*;

import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;

@Timeout(10)
class AtomicLedgerTest {
    @Test
    void reserveNeverOverdraws() throws Exception {
        var ledger = new AtomicLedger(100);
        var start = new CountDownLatch(1);
        var accepted = new AtomicInteger();
        try (var pool = Executors.newFixedThreadPool(4)) {
            var jobs = new ArrayList<Future<?>>();
            for (int t = 0; t < 4; t++)
                jobs.add(
                        pool.submit(
                                () -> {
                                    start.await();
                                    for (int i = 0; i < 50; i++)
                                        if (ledger.reserve(1)) accepted.incrementAndGet();
                                    return null;
                                }));
            start.countDown();
            for (var job : jobs) job.get(3, TimeUnit.SECONDS);
        }
        assertEquals(100, accepted.get());
        assertEquals(0, ledger.balance());
        assertFalse(ledger.reserve(1));
        ledger.add(3);
        assertTrue(ledger.reserve(3));
        assertEquals(0, ledger.balance());
    }

    @Test
    void validationAndOverflowPreserveState() {
        assertThrows(IllegalArgumentException.class, () -> new AtomicLedger(-1));
        var l = new AtomicLedger(Integer.MAX_VALUE);
        assertThrows(IllegalArgumentException.class, () -> l.reserve(0));
        assertThrows(IllegalArgumentException.class, () -> l.add(-1));
        assertThrows(ArithmeticException.class, () -> l.add(1));
        assertEquals(Integer.MAX_VALUE, l.balance());
    }

    @Test
    void abaIsRejectedByVersionEvenWhenReferenceReturns() {
        String a = new String("A"), b = new String("B");
        var plain = new AtomicReference<>(a);
        var old = plain.get();
        assertTrue(plain.compareAndSet(a, b));
        assertTrue(plain.compareAndSet(b, a));
        assertTrue(plain.compareAndSet(old, "旧操作仍成功"));
        var stamped = new AtomicLedger.VersionedSlot(a);
        var first = stamped.snapshot();
        assertTrue(stamped.replace(first, b));
        assertTrue(stamped.replace(stamped.snapshot(), a));
        assertSame(a, stamped.snapshot().value());
        assertEquals(2, stamped.snapshot().version());
        assertFalse(stamped.replace(first, "旧操作必须失败"));
    }

    @Test
    void completedCountersHaveExactTotals() throws Exception {
        var counts = new AtomicLedger.Counters();
        assertEquals(0, counts.count("不存在"));
        try (var pool = Executors.newFixedThreadPool(4)) {
            var work = new ArrayList<Future<?>>();
            for (int t = 0; t < 4; t++)
                work.add(
                        pool.submit(
                                () -> {
                                    for (int i = 0; i < 100; i++) {
                                        counts.increment("订单");
                                        counts.increment("付款");
                                    }
                                }));
            for (var f : work) f.get(3, TimeUnit.SECONDS);
        }
        assertEquals(Map.of("订单", 400L, "付款", 400L), counts.snapshot());
        assertThrows(UnsupportedOperationException.class, () -> counts.snapshot().put("错误", 1L));
        assertThrows(NullPointerException.class, () -> counts.increment(null));
    }
}
