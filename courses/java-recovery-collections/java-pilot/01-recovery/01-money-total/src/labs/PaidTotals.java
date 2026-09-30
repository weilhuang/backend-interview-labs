// 标准实现位于作者占位区；学员填写同一公开接口，题面末尾提供完整答案与解析。
package labs;
import java.util.List;
import java.util.Objects;
public final class PaidTotals {
    public enum Status { PAID, CANCELLED, PENDING }
    public record Order(long cents, Status status) {}
    private PaidTotals() {}
    public static long total(List<Order> orders) {
        Objects.requireNonNull(orders, "orders");
        long sum = 0;
        for (Order order : orders) {
            Objects.requireNonNull(order, "order");
            Objects.requireNonNull(order.status(), "status");
            if (order.cents() < 0) throw new IllegalArgumentException("negative cents");
            if (order.status() == Status.PAID) sum = Math.addExact(sum, order.cents());
        }
        return sum;
    }
}
