import static org.junit.jupiter.api.Assertions.*;

import labs.foundation.*;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.Timeout;

import java.util.*;
import java.util.concurrent.*;

@Timeout(5)
class OrderedQueriesTest {
    private Order order(String id, long cents) {
        return new Order(id, "甲", cents, Order.Status.PAID);
    }

    @Test
    void rangeBoundariesAndTopKTies() {
        var values = List.of(order("z", 2), order("b", 5), order("a", 5), order("x", 9));
        assertEquals(
                List.of(values.get(1), values.get(2)), OrderedQueries.priceRange(values, 5, 9));
        assertEquals(List.of(values.get(3), values.get(2)), OrderedQueries.topK(values, 2));
        assertEquals(List.of(), OrderedQueries.topK(values, 0));
        assertEquals(4, OrderedQueries.topK(values, 99).size());
        assertThrows(IllegalArgumentException.class, () -> OrderedQueries.topK(values, -1));
    }

    @Test
    void comparatorLawAndExtremeValues() {
        Comparator<Order> comparator =
                Comparator.comparingLong(Order::cents).reversed().thenComparing(Order::id);
        var values =
                List.of(order("a", 0), order("b", Integer.MAX_VALUE), order("c", Long.MAX_VALUE));
        for (var a : values)
            for (var b : values) {
                assertEquals(
                        -Integer.signum(comparator.compare(a, b)),
                        Integer.signum(comparator.compare(b, a)));
                for (var c : values)
                    if (comparator.compare(a, b) <= 0 && comparator.compare(b, c) <= 0)
                        assertTrue(comparator.compare(a, c) <= 0);
            }
        assertEquals(
                List.of(values.get(2), values.get(1), values.get(0)),
                OrderedQueries.topK(values, 3));
    }

    @Test
    void lruAccessAndEviction() {
        var cache = new OrderedQueries.Lru<String, Integer>(2);
        cache.put("a", 1);
        cache.put("b", 2);
        assertEquals(Optional.of(1), cache.get("a"));
        cache.put("c", 3);
        assertEquals(List.of("a", "c"), cache.oldestFirst());
        assertTrue(cache.get("b").isEmpty());
        cache.put("a", 9);
        assertEquals(List.of("c", "a"), cache.oldestFirst());
    }

    @Test
    void topKAgainstFullSort() {
        var random = new Random(106);
        List<Order> values = new ArrayList<>();
        for (int i = 0; i < 100; i++) values.add(order("id" + i, random.nextInt(20)));
        var sorted =
                values.stream()
                        .sorted(
                                Comparator.comparingLong(Order::cents)
                                        .reversed()
                                        .thenComparing(Order::id))
                        .toList();
        for (int k = 0; k < 110; k++)
            assertEquals(sorted.subList(0, Math.min(k, 100)), OrderedQueries.topK(values, k));
    }
}
