package labs.foundation;

import java.util.*;

public final class Workspace {
    private Workspace() {}

    public static long paidTotal(List<Order> orders) {
        // 作答开始
        Objects.requireNonNull(orders, "订单列表不能为空");
        long sum = 0;
        for (int i = 0; i < orders.size(); i++) {
            Order order = Objects.requireNonNull(orders.get(i));
            if (order.status() == Order.Status.PAID) sum = Math.addExact(sum, order.cents());
        }
        return sum;
        // 作答结束
    }
}
