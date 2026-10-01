package labs.foundation;

import java.util.*;

public final class OrderCodec {
    private OrderCodec() {}

    public static Order parse(String text, int line) {
        Objects.requireNonNull(text, "输入行不能为空");
        if (line < 1) throw new IllegalArgumentException("行号从1开始");
        if (text.length() > 512) throw new ParseFailure(line, "整行", "超过512字符");
        String[] parts = text.split("[|]", -1);
        if (parts.length != 4) throw new ParseFailure(line, "整行", "必须有4个字段");
        for (int i = 0; i < parts.length; i++) parts[i] = parts[i].strip();
        if (parts[0].isEmpty()) throw new ParseFailure(line, "id", "不能为空");
        if (parts[1].isEmpty()) throw new ParseFailure(line, "customer", "不能为空");
        long cents;
        try {
            cents = Long.parseLong(parts[2]);
        } catch (NumberFormatException e) {
            throw new ParseFailure(line, "cents", "必须是long范围内整数");
        }
        if (cents < 0) throw new ParseFailure(line, "cents", "不能为负");
        Order.Status status;
        try {
            status = Order.Status.valueOf(parts[3]);
        } catch (IllegalArgumentException e) {
            throw new ParseFailure(line, "status", "只允许PAID或PENDING");
        }
        return new Order(parts[0], parts[1], cents, status);
    }

    public static List<Order> parseBatch(List<String> lines) {
        Objects.requireNonNull(lines);
        if (lines.size() > 10000) throw new IllegalArgumentException("批次最多10000行");
        List<Order> result = new ArrayList<>();
        Set<String> seen = new HashSet<>();
        for (int i = 0; i < lines.size(); i++) {
            Order order = parse(lines.get(i), i + 1);
            if (!seen.add(order.id())) throw new ParseFailure(i + 1, "id", "重复订单ID");
            result.add(order);
        }
        return List.copyOf(result);
    }
}
