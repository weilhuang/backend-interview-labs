package labs.foundation;

import java.util.*;
import java.util.function.*;
import java.util.stream.*;

public final class Repositories {
    private Repositories() {}

    public interface Repository<K, V> {
        Optional<V> find(K key);

        void saveAll(Iterable<? extends V> values);

        void copyInto(Collection<? super V> target);
    }

    public static final class MemoryRepository<K, V> implements Repository<K, V> {
        private final Function<? super V, ? extends K> keyOf;
        private final Map<K, V> data = new LinkedHashMap<>();

        public MemoryRepository(Function<? super V, ? extends K> keyOf) {
            this.keyOf = Objects.requireNonNull(keyOf);
        }

        public Optional<V> find(K key) {
            return Optional.ofNullable(data.get(Objects.requireNonNull(key)));
        }

        public void saveAll(Iterable<? extends V> values) {
            // 作答开始
            Map<K, V> staged = new LinkedHashMap<>();
            for (V v : Objects.requireNonNull(values)) {
                Objects.requireNonNull(v);
                staged.put(Objects.requireNonNull(keyOf.apply(v)), v);
                if (staged.size() > 4096) throw new IllegalArgumentException("批次超限");
            }
            Set<K> keys = new HashSet<>(data.keySet());
            keys.addAll(staged.keySet());
            if (keys.size() > 4096) throw new IllegalStateException("仓库最多4096项");
            data.putAll(staged);
            // 作答结束
        }

        public void copyInto(Collection<? super V> target) {
            Objects.requireNonNull(target).addAll(data.values());
        }
    }

    public static Map<String, Long> loopTotals(List<Order> orders) {
        Map<String, Long> result = new TreeMap<>();
        for (Order o : orders)
            if (o.status() == Order.Status.PAID)
                result.merge(o.customer(), o.cents(), Math::addExact);
        return result;
    }

    public static Map<String, Long> streamTotals(List<Order> orders) {
        // 作答开始
        return loopTotals(orders);
        // 作答结束
    }

    public static List<Order> stableByAmount(List<Order> orders) {
        return orders.stream().sorted(Comparator.comparingLong(Order::cents)).toList();
    }
}
