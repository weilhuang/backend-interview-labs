package labs.foundation;

import java.util.*;
import java.util.concurrent.*;

public final class ConcurrentViews {
    private ConcurrentViews() {}

    public static int removeNegatives(List<Integer> values) {
        // 作答开始
        int before = values.size();
        values.removeIf(value -> Objects.requireNonNull(value) < 0);
        return before - values.size();
        // 作答结束
    }

    public static void increment(ConcurrentHashMap<String, Long> counters, String key) {
        // 作答开始
        counters.compute(
                Objects.requireNonNull(key),
                (ignored, old) -> old == null ? 1L : Math.addExact(old, 1L));
        // 作答结束
    }

    public static <T> List<T> collect(Iterator<T> iterator) {
        List<T> values = new ArrayList<>();
        iterator.forEachRemaining(values::add);
        return List.copyOf(values);
    }
}
