package labs.jvm;

import java.time.*;
import java.util.*;

public final class MigrationReport {
    public enum Status {
        PAID,
        PENDING
    }

    public record Order(String id, long cents, Instant created, Status status) {
        public Order {
            Objects.requireNonNull(id);
            Objects.requireNonNull(created);
            Objects.requireNonNull(status);
            if (cents < 0) throw new IllegalArgumentException("金额不得为负");
        }
    }

    public sealed interface Outcome permits Found, Missing {}

    public record Found(Order order) implements Outcome {}

    public record Missing(String id) implements Outcome {}

    private MigrationReport() {}

    public static long total(List<Order> orders, LocalDate day, ZoneId zone) {
        // 作答开始
        Objects.requireNonNull(orders);
        Objects.requireNonNull(day);
        Objects.requireNonNull(zone);
        var start = day.atStartOfDay(zone).toInstant();
        var end = day.plusDays(1).atStartOfDay(zone).toInstant();
        long sum = 0;
        for (Order o : orders)
            if (o.status() == Status.PAID
                    && !o.created().isBefore(start)
                    && o.created().isBefore(end)) sum = Math.addExact(sum, o.cents());
        return sum;
        // 作答结束
    }

    public static Optional<Order> find(List<Order> orders, String id) {
        Objects.requireNonNull(id);
        return orders.stream().filter(o -> id.equals(o.id())).findFirst();
    }

    public static Outcome outcome(List<Order> orders, String id) {
        return find(orders, id).<Outcome>map(Found::new).orElseGet(() -> new Missing(id));
    }

    public static String label(Status status) {
        return switch (status) {
            case PAID -> "已付款";
            case PENDING -> "待付款";
        };
    }

    public static String explain(Outcome outcome) {
        if (outcome instanceof Found found) return found.order().id();
        return ((Missing) outcome).id() + "未找到";
    }
}
