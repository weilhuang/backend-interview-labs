package labs.foundation;

public final class CollectionViewsUsage {
    public static void main(String[] args) {
        var orders =
                java.util.List.of(
                        new Order("A", "甲", 1, Order.Status.PAID),
                        new Order("A", "甲", 2, Order.Status.PAID));
        System.out.println("稳定去重=" + CollectionViews.stableIds(orders));
        System.out.println("排队分发=" + CollectionViews.dispatch(orders));
    }
}
