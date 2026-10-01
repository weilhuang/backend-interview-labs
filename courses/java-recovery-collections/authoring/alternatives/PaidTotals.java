package labs;
import java.util.List;
import java.util.Objects;
public final class PaidTotals {
    public enum Status { PAID, CANCELLED, PENDING }
    public record Order(long cents, Status status) {}
    private PaidTotals() {}
    public static long total(List<Order> orders) {
        Objects.requireNonNull(orders, "orders");
        
        for (Order order : orders) {
            Objects.requireNonNull(order, "order");
            Objects.requireNonNull(order.status(), "status");
            if (order.cents() < 0) throw new IllegalArgumentException("negative cents");

        }
        return orders.stream().filter(order -> order.status() == Status.PAID)
            .mapToLong(Order::cents).reduce(0L, Math::addExact);
    }
}
