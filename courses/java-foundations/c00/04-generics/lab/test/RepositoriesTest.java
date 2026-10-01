import static org.junit.jupiter.api.Assertions.*;

import labs.foundation.*;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.Timeout;

import java.util.*;
import java.util.concurrent.*;

@Timeout(5)
class RepositoriesTest {
    @Test
    void pecsAndAtomicSave() {
        Repositories.Repository<Number, Number> repo = new Repositories.MemoryRepository<>(x -> x);
        repo.saveAll(List.of(1, 2));
        List<Object> destination = new ArrayList<>();
        repo.copyInto(destination);
        assertEquals(List.of(1, 2), destination);
        assertEquals(Optional.of(1), repo.find(1));
        assertTrue(repo.find(99).isEmpty());
        assertThrows(NullPointerException.class, () -> repo.saveAll(Arrays.asList(3, null)));
        assertTrue(repo.find(3).isEmpty(), "批次非法不得部分写入");
    }

    @Test
    void loopAndStreamAndStableTies() {
        var a = new Order("A", "乙", 4, Order.Status.PAID);
        var b = new Order("B", "甲", 4, Order.Status.PAID);
        var values = List.of(a, b, new Order("C", "甲", 50, Order.Status.PENDING));
        assertEquals(Map.of("甲", 4L, "乙", 4L), Repositories.streamTotals(values));
        assertEquals(Repositories.loopTotals(values), Repositories.streamTotals(values));
        assertEquals(List.of(a, b, values.get(2)), Repositories.stableByAmount(values));
    }

    @Test
    void lazinessAndOverflow() {
        var calls = new java.util.concurrent.atomic.AtomicInteger();
        var stream =
                List.of(1, 2).stream()
                        .filter(
                                v -> {
                                    calls.incrementAndGet();
                                    return true;
                                });
        assertEquals(0, calls.get());
        assertEquals(2, stream.count());
        assertEquals(2, calls.get());
        var data =
                List.of(
                        new Order("A", "甲", Long.MAX_VALUE, Order.Status.PAID),
                        new Order("B", "甲", 1, Order.Status.PAID));
        assertThrows(ArithmeticException.class, () -> Repositories.streamTotals(data));
    }
}
