package labs.foundation;

public final class ConcurrentViewsUsage {
    public static void main(String[] args) {
        var counters = new java.util.concurrent.ConcurrentHashMap<String, Long>();
        ConcurrentViews.increment(counters, "A");
        ConcurrentViews.increment(counters, "A");
        System.out.println("原子累计=" + counters);
        var list = new java.util.ArrayList<>(java.util.List.of(-1, 2, -3));
        System.out.println("删除=" + ConcurrentViews.removeNegatives(list) + "，剩余=" + list);
    }
}
