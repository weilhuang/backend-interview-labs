package labs.foundation;

public final class OrderedQueriesUsage {
    public static void main(String[] args) {
        var orders =
                java.util.List.of(
                        new Order("A", "甲", 100, Order.Status.PAID),
                        new Order("B", "乙", 300, Order.Status.PAID));
        System.out.println("最高金额=" + OrderedQueries.topK(orders, 1));
        System.out.println("范围=" + OrderedQueries.priceRange(orders, 100, 300));
    }
}
