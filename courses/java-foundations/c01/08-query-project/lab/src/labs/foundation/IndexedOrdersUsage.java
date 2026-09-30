package labs.foundation;

public final class IndexedOrdersUsage {
    public static void main(String[] args) {
        var index =
                new IndexedOrders(
                        java.util.List.of(
                                new Order("A", "甲", 120, Order.Status.PAID),
                                new Order("B", "乙", 200, Order.Status.PAID)),
                        2);
        System.out.println("查询=" + index.query("甲", 100));
        System.out.println("Top客户=" + index.topCustomers(1));
        index.query("甲", 100);
        System.out.println("缓存命中=" + index.hits());
    }
}
