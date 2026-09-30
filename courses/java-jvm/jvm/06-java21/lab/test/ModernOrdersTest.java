import static org.junit.jupiter.api.Assertions.*;

import labs.jvm.*;

import org.junit.jupiter.api.*;

@Timeout(8)
class ModernOrdersTest {
    @Test
    void exhaustiveAmounts() {
        assertEquals(
                20, ModernOrders.delta(new ModernOrders.Paid("a", new ModernOrders.Money(20))));
        assertEquals(
                -9, ModernOrders.delta(new ModernOrders.Refund("a", new ModernOrders.Money(9))));
        assertEquals(0, ModernOrders.delta(new ModernOrders.Cancelled("a")));
        assertThrows(NullPointerException.class, () -> ModernOrders.delta(null));
        assertThrows(IllegalArgumentException.class, () -> new ModernOrders.Money(-1));
    }

    @Test
    void sequenceSnapshotAndViews() {
        var input = new java.util.ArrayList<>(java.util.List.of("a", "b", "c"));
        var result = ModernOrders.newest(input, 2);
        input.clear();
        assertEquals(java.util.List.of("c", "b"), result);
        assertThrows(UnsupportedOperationException.class, () -> result.add("x"));
        assertEquals(java.util.List.of(), ModernOrders.newest(input, 3));
        assertThrows(IllegalArgumentException.class, () -> ModernOrders.newest(input, -1));
        var ordered = new java.util.LinkedHashSet<>(java.util.List.of("a", "b"));
        assertEquals(java.util.List.of("b", "a"), ModernOrders.newest(ordered, 9));
        var list = new java.util.ArrayList<>(java.util.List.of(1, 2));
        list.reversed().addFirst(3);
        assertEquals(java.util.List.of(1, 2, 3), list, "reversed本身是视图，本方法输出才是快照");
    }

    @Test
    void workRunsOnVirtualThread() throws Exception {
        assertEquals(
                java.util.List.of(4, 9),
                ModernOrders.boundedMap(
                        java.util.List.of(2, 3),
                        2,
                        n -> {
                            assertTrue(Thread.currentThread().isVirtual(), "每个业务任务必须使用虚拟线程");
                            return n * n;
                        }));
    }

    @Test
    void finiteVirtualThreadTasks() throws Exception {
        assertEquals(
                java.util.List.of(9, 1, 4),
                ModernOrders.boundedSquares(java.util.List.of(3, -1, 2), 2));
        assertEquals(java.util.List.of(), ModernOrders.boundedSquares(java.util.List.of(), 1));
        assertThrows(
                IllegalArgumentException.class,
                () -> ModernOrders.boundedSquares(java.util.Collections.nCopies(65, 1), 2));
        assertThrows(
                IllegalArgumentException.class,
                () -> ModernOrders.boundedSquares(java.util.List.of(1), 0));
        var e =
                assertThrows(
                        java.util.concurrent.ExecutionException.class,
                        () -> ModernOrders.boundedSquares(java.util.List.of(50000), 2));
        assertInstanceOf(ArithmeticException.class, e.getCause());
    }
}
