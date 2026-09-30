package labs.foundation;

public final class MiniHashMapUsage {
    public static void main(String[] args) {
        var map = new MiniHashMap<String, Integer>();
        map.put("A", 1);
        System.out.println("替换旧值=" + map.put("A", 2));
        map.put(null, 3);
        System.out.println("空键=" + map.get(null) + "，数量=" + map.size());
    }
}
