package labs.foundation;

import java.util.*;

public final class Workspace {
    private Workspace() {}

    public static long paidTotal(List<Order> orders) {
        // 作答开始
        Objects.requireNonNull(orders, "订单列表不能为空");
        long sum = 0;
        for (Order order : orders)
            if (Objects.requireNonNull(order, "订单不能为空").status() == Order.Status.PAID)
                sum = Math.addExact(sum, order.cents());
        return sum;
        // 作答结束
    }
}
