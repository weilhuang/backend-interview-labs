package labs.foundation;

import java.util.*;

public final class CollectionViews {
    private CollectionViews() {}

    public static List<String> stableIds(List<Order> orders) {
        // 作答开始
        List<String> ids = new ArrayList<>();
        Set<String> seen = new HashSet<>();
        for (Order order : orders)
            if (seen.add(Objects.requireNonNull(order).id())) ids.add(order.id());
        return List.copyOf(ids);
        // 作答结束
    }

    public static <T> List<T> snapshot(List<T> input, int from, int to) {
        // 作答开始
        Objects.checkFromToIndex(from, to, input.size());
        return Collections.unmodifiableList(new ArrayList<>(input.subList(from, to)));
        // 作答结束
    }

    public static List<String> dispatch(List<Order> orders) {
        Deque<Order> queue = new ArrayDeque<>(orders);
        List<String> ids = new ArrayList<>();
        while (!queue.isEmpty()) ids.add(queue.removeFirst().id());
        return ids;
    }

    public static Map<String, Order> firstById(List<Order> orders) {
        Map<String, Order> result = new LinkedHashMap<>();
        for (Order order : orders) result.putIfAbsent(order.id(), order);
        return result;
    }
}
