package labs.foundation;

import java.util.*;
import java.util.concurrent.*;

public final class ConcurrentViews {
    private ConcurrentViews() {}

    public static int removeNegatives(List<Integer> values) {
        // 作答开始
        int removed = 0;
        for (Iterator<Integer> it = values.iterator(); it.hasNext(); )
            if (Objects.requireNonNull(it.next()) < 0) {
                it.remove();
                removed++;
            }
        return removed;
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
