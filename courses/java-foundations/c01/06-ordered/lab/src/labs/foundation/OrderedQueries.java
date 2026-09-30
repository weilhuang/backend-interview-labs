package labs.foundation;

import java.util.*;

public final class OrderedQueries {
    private OrderedQueries() {}

    public static List<Order> priceRange(List<Order> orders, long from, long to) {
        if (from < 0 || to < from) throw new IllegalArgumentException("金额半开区间非法");
        NavigableMap<Long, List<Order>> index = new TreeMap<>();
        for (Order o : orders) index.computeIfAbsent(o.cents(), k -> new ArrayList<>()).add(o);
        return index.subMap(from, true, to, false).values().stream().flatMap(List::stream).toList();
    }

    public static List<Order> topK(List<Order> orders, int k) {
        // 作答开始
        if (k < 0) throw new IllegalArgumentException("k不能为负");
        if (k == 0) return List.of();
        Comparator<Order> worst =
                Comparator.comparingLong(Order::cents)
                        .thenComparing(Order::id, Comparator.reverseOrder());
        PriorityQueue<Order> heap = new PriorityQueue<>(worst);
        for (Order o : orders) {
            heap.add(o);
            if (heap.size() > k) heap.remove();
        }
        return heap.stream().sorted(worst.reversed()).toList();
        // 作答结束
    }

    public static final class Lru<K, V> {
        private final int capacity;
        private final LinkedHashMap<K, V> entries = new LinkedHashMap<>(16, .75f, true);

        public Lru(int capacity) {
            if (capacity < 1 || capacity > 128) throw new IllegalArgumentException("容量须为1至128");
            this.capacity = capacity;
        }

        public void put(K key, V value) {
            entries.put(Objects.requireNonNull(key), Objects.requireNonNull(value));
            if (entries.size() > capacity) entries.pollFirstEntry();
        }

        public Optional<V> get(K key) {
            return Optional.ofNullable(entries.get(Objects.requireNonNull(key)));
        }

        public List<K> oldestFirst() {
            return List.copyOf(entries.keySet());
        }
    }
}
