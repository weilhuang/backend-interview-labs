package labs.foundation;

import java.util.*;

public final class IndexedOrders {
    public record Query(String customer, long minimum) {
        public Query {
            Objects.requireNonNull(customer);
            if (minimum < 0) throw new IllegalArgumentException("最低金额非负");
        }
    }

    private final Map<String, List<Order>> byCustomer;
    private final Map<String, Order> byId;
    private final LinkedHashMap<Query, List<Order>> cache = new LinkedHashMap<>(16, .75f, true);
    private final int capacity;
    private long hits, misses;

    public IndexedOrders(List<Order> orders, int capacity) {
        if (capacity < 1 || capacity > 16 || orders.size() > 4096)
            throw new IllegalArgumentException("缓存1至16、订单最多4096");
        this.capacity = capacity;
        Map<String, Order> ids = new HashMap<>();
        Map<String, List<Order>> customers = new HashMap<>();
        for (Order order : orders) {
            Objects.requireNonNull(order);
            if (ids.putIfAbsent(order.id(), order) != null)
                throw new IllegalArgumentException("订单ID重复");
            customers.computeIfAbsent(order.customer(), ignored -> new ArrayList<>()).add(order);
        }
        Map<String, List<Order>> frozen = new HashMap<>();
        customers.forEach((customer, list) -> frozen.put(customer, List.copyOf(list)));
        byCustomer = Map.copyOf(frozen);
        byId = Map.copyOf(ids);
    }

    public Optional<Order> find(String id) {
        return Optional.ofNullable(byId.get(Objects.requireNonNull(id)));
    }

    public List<Order> query(String customer, long minimum) {
        // 作答开始
        Query key = new Query(customer, minimum);
        List<Order> result = cache.get(key);
        if (result != null) {
            hits++;
            return result;
        }
        misses++;
        result =
                byCustomer.getOrDefault(customer, List.of()).stream()
                        .filter(o -> o.cents() >= minimum)
                        .sorted(Comparator.comparing(Order::id))
                        .toList();
        cache.put(key, result);
        if (cache.size() > capacity) cache.pollFirstEntry();
        return result;
        // 作答结束
    }

    public record CustomerTotal(String customer, long cents) {}

    public List<CustomerTotal> topCustomers(int k) {
        // 作答开始
        if (k < 0) throw new IllegalArgumentException("k非负");
        if (k == 0) return List.of();
        Comparator<CustomerTotal> worst =
                Comparator.comparingLong(CustomerTotal::cents)
                        .thenComparing(CustomerTotal::customer, Comparator.reverseOrder());
        PriorityQueue<CustomerTotal> heap = new PriorityQueue<>(worst);
        for (var entry : byCustomer.entrySet()) {
            long total = 0;
            for (Order o : entry.getValue())
                if (o.status() == Order.Status.PAID) total = Math.addExact(total, o.cents());
            heap.add(new CustomerTotal(entry.getKey(), total));
            if (heap.size() > k) heap.remove();
        }
        return heap.stream().sorted(worst.reversed()).toList();
        // 作答结束
    }

    public List<Query> cachedOldestFirst() {
        return List.copyOf(cache.keySet());
    }

    public long hits() {
        return hits;
    }

    public long misses() {
        return misses;
    }
}
