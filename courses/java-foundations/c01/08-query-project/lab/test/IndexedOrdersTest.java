import static org.junit.jupiter.api.Assertions.*;

import labs.foundation.*;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.Timeout;

import java.util.*;
import java.util.concurrent.*;

@Timeout(5)
class IndexedOrdersTest {
    private List<Order> fixture() {
        return List.of(
                new Order("C", "乙", 5, Order.Status.PAID),
                new Order("B", "甲", 3, Order.Status.PENDING),
                new Order("A", "甲", 5, Order.Status.PAID));
    }

    @Test
    void indexedSnapshotAndCacheEviction() {
        var mutable = new ArrayList<>(fixture());
        var index = new IndexedOrders(mutable, 2);
        mutable.clear();
        assertEquals(List.of("A", "B"), index.query("甲", 0).stream().map(Order::id).toList());
        index.query("乙", 0);
        index.query("甲", 0);
        index.query("甲", 5);
        assertEquals(
                List.of(new IndexedOrders.Query("甲", 0), new IndexedOrders.Query("甲", 5)),
                index.cachedOldestFirst());
        assertEquals(1, index.hits());
        assertEquals(3, index.misses());
        assertThrows(UnsupportedOperationException.class, () -> index.query("甲", 0).clear());
        assertEquals("A", index.find("A").orElseThrow().id());
        assertTrue(index.find("不存在").isEmpty());
    }

    @Test
    void topKTieAndInvalid() {
        var index = new IndexedOrders(fixture(), 2);
        assertEquals(
                List.of(
                        new IndexedOrders.CustomerTotal("乙", 5),
                        new IndexedOrders.CustomerTotal("甲", 5)),
                index.topCustomers(9));
        assertThrows(IllegalArgumentException.class, () -> index.query("甲", -1));
        assertThrows(
                IllegalArgumentException.class,
                () -> new IndexedOrders(List.of(fixture().get(0), fixture().get(0)), 2));
        assertEquals(List.of(), index.topCustomers(0));
    }

    @Test
    void differentialAgainstScan() {
        var random = new Random(108);
        List<Order> orders = new ArrayList<>();
        for (int i = 0; i < 300; i++)
            orders.add(
                    new Order(
                            "id" + i,
                            "客" + random.nextInt(8),
                            random.nextInt(100),
                            Order.Status.PAID));
        var index = new IndexedOrders(orders, 4);
        for (int j = 0; j < 80; j++) {
            String customer = "客" + random.nextInt(9);
            long min = random.nextInt(101);
            var expected =
                    orders.stream()
                            .filter(o -> o.customer().equals(customer) && o.cents() >= min)
                            .sorted(Comparator.comparing(Order::id))
                            .toList();
            assertEquals(expected, index.query(customer, min));
            assertTrue(index.cachedOldestFirst().size() <= 4);
        }
    }
}
