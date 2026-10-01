package labs.capstone;

import static labs.capstone.Model.*;

import java.util.*;

/** C14-05：审计只报告事实，不静默修改库存；读模型落后与库存破坏必须区别对待。 */
public final class Audit {
    private Audit() {}

    public record Finding(String severity, String subject, String detail) {}

    public static List<Finding> inspect(
            List<Stock> stocks, List<Order> orders, List<Delivery> deliveries) {
        // 学习区开始
        List<Finding> findings = new ArrayList<>();
        Map<String, Long> reserved = new HashMap<>();
        for (Order order : orders) {
            if (order.quantity() < 1
                    || (!order.status().equals("RESERVED") && !order.status().equals("CANCELLED")))
                findings.add(new Finding("ERROR", order.requestId(), "非法订单状态或数量"));
            if (order.status().equals("RESERVED"))
                reserved.merge(order.sku(), (long) order.quantity(), Long::sum);
        }
        Set<String> known = new HashSet<>();
        for (Stock stock : stocks) {
            known.add(stock.sku());
            long held = reserved.getOrDefault(stock.sku(), 0L);
            if (stock.available() < 0 || (long) stock.available() + held != stock.initial())
                findings.add(new Finding("ERROR", stock.sku(), "可售库存与已保留数量不守恒"));
        }
        for (String sku : reserved.keySet())
            if (!known.contains(sku)) findings.add(new Finding("ERROR", sku, "订单引用不存在的库存"));
        Map<String, Delivery> byRequest = new HashMap<>();
        for (Delivery delivery : deliveries) byRequest.put(delivery.requestId(), delivery);
        Set<String> orderIds = new HashSet<>();
        for (Order order : orders) {
            orderIds.add(order.requestId());
            Delivery projection = byRequest.get(order.requestId());
            if (projection == null || projection.version() < order.version())
                findings.add(new Finding("LAG", order.requestId(), "读模型待重放追平"));
            else if (projection.version() != order.version()
                    || !projection.status().equals(order.status()))
                findings.add(new Finding("ERROR", order.requestId(), "读模型超前或同版本状态冲突"));
        }
        for (Delivery delivery : deliveries)
            if (!orderIds.contains(delivery.requestId()))
                findings.add(new Finding("ERROR", delivery.requestId(), "读模型没有来源订单"));
        return List.copyOf(findings);
        // 学习区结束
    }
}
