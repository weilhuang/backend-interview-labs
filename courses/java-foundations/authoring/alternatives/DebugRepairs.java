package labs.foundation;

import java.util.*;
import java.util.concurrent.Callable;

public final class DebugRepairs {
    private DebugRepairs() {}

    public static <T> List<T> slice(List<T> values, int from, int to) {
        // 作答开始
        Objects.checkFromToIndex(from, to, values.size());
        return List.copyOf(values.subList(from, to));
        // 作答结束
    }

    public static List<List<String>> snapshot(List<List<String>> values) {
        // 作答开始
        List<List<String>> result = new ArrayList<>();
        for (List<String> row : values) result.add(List.copyOf(row));
        return List.copyOf(result);
        // 作答结束
    }

    public static <T> T withResource(AutoCloseable resource, Callable<T> operation)
            throws Exception {
        // 作答开始
        try (resource) {
            return operation.call();
        }
        // 作答结束
    }
}
