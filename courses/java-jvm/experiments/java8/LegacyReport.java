import java.time.*;
import java.util.*;

public final class LegacyReport {
    public static final class Order {
        final String id;
        final long cents;
        final Instant created;
        final boolean paid;

        Order(String id, long cents, Instant created, boolean paid) {
            if (cents < 0) throw new IllegalArgumentException("金额非负");
            this.id = Objects.requireNonNull(id);
            this.cents = cents;
            this.created = Objects.requireNonNull(created);
            this.paid = paid;
        }
    }

    public static long total(List<Order> orders, LocalDate day, ZoneId zone) {
        Instant start = day.atStartOfDay(zone).toInstant(),
                end = day.plusDays(1).atStartOfDay(zone).toInstant();
        long sum = 0;
        for (Order order : orders)
            if (order.paid && !order.created.isBefore(start) && order.created.isBefore(end))
                sum = Math.addExact(sum, order.cents);
        return sum;
    }

    public static void main(String[] args) {
        Order order = new Order("A", 300, Instant.parse("2024-03-10T05:00:00Z"), true);
        System.out.println(
                total(
                        Arrays.asList(order),
                        LocalDate.of(2024, 3, 10),
                        ZoneId.of("America/New_York")));
    }
}
