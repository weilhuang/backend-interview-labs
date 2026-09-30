package labs.capstone;

import static labs.capstone.Model.*;

import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;

import java.util.*;

class AuditTest {
    @Test
    void 守恒且投影同步没有异常() {
        assertTrue(
                Audit.inspect(
                                List.of(new Stock("book", 20, 18)),
                                List.of(new Order("A", "book", 2, "RESERVED", 1)),
                                List.of(new Delivery("A:1", "A", "RESERVED", 1)))
                        .isEmpty());
    }

    @Test
    void 取消订单不计入占用库存() {
        assertTrue(
                Audit.inspect(
                                List.of(new Stock("book", 20, 20)),
                                List.of(new Order("A", "book", 2, "CANCELLED", 2)),
                                List.of(new Delivery("A:2", "A", "CANCELLED", 2)))
                        .isEmpty());
    }

    @Test
    void 落后是可恢复的延迟而非超卖() {
        var f =
                Audit.inspect(
                        List.of(new Stock("book", 20, 18)),
                        List.of(new Order("A", "book", 2, "RESERVED", 1)),
                        List.of());
        assertEquals(List.of("LAG"), f.stream().map(Audit.Finding::severity).toList());
    }

    @Test
    void 同版本冲突与超前都是错误() {
        for (var d :
                List.of(
                        new Delivery("A:1", "A", "CANCELLED", 1),
                        new Delivery("A:2", "A", "CANCELLED", 2)))
            assertTrue(
                    Audit.inspect(
                                    List.of(new Stock("book", 20, 18)),
                                    List.of(new Order("A", "book", 2, "RESERVED", 1)),
                                    List.of(d))
                            .stream()
                            .anyMatch(f -> f.severity().equals("ERROR")));
    }

    @Test
    void 不存在的商品和无来源投影必须报警() {
        var f =
                Audit.inspect(
                        List.of(),
                        List.of(new Order("A", "missing", 1, "RESERVED", 1)),
                        List.of(new Delivery("B:1", "B", "RESERVED", 1)));
        assertTrue(
                f.stream()
                        .anyMatch(
                                x ->
                                        x.subject().equals("missing")
                                                && x.severity().equals("ERROR")));
        assertTrue(
                f.stream().anyMatch(x -> x.subject().equals("B") && x.severity().equals("ERROR")));
    }

    @Test
    void 不允许负库存或把长整型累计截断() {
        var f = Audit.inspect(List.of(new Stock("book", 20, -1)), List.of(), List.of());
        assertTrue(f.stream().anyMatch(x -> x.severity().equals("ERROR")));
        var huge =
                List.of(
                        new Order("A", "book", Integer.MAX_VALUE, "RESERVED", 1),
                        new Order("B", "book", Integer.MAX_VALUE, "RESERVED", 1));
        assertTrue(
                Audit.inspect(List.of(new Stock("book", 0, 2)), huge, List.of()).stream()
                        .anyMatch(x -> x.severity().equals("ERROR")));
    }

    @Test
    void 随机取消组合始终守恒且返回只读报告() {
        var random = new Random(1405);
        for (int trial = 0; trial < 100; trial++) {
            var orders = new ArrayList<Order>();
            var projection = new ArrayList<Delivery>();
            int held = 0;
            for (int i = 0; i < 10; i++) {
                boolean reserved = random.nextBoolean();
                int qty = random.nextInt(5) + 1;
                String state = reserved ? "RESERVED" : "CANCELLED";
                long version = reserved ? 1 : 2;
                orders.add(new Order("o" + i, "book", qty, state, version));
                projection.add(new Delivery("o" + i + ":" + version, "o" + i, state, version));
                if (reserved) held += qty;
            }
            assertTrue(
                    Audit.inspect(List.of(new Stock("book", 50, 50 - held)), orders, projection)
                            .isEmpty());
        }
        assertThrows(
                UnsupportedOperationException.class,
                () ->
                        Audit.inspect(List.of(), List.of(), List.of())
                                .add(new Audit.Finding("ERROR", "x", "x")));
    }
}
