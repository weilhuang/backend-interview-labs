package labs.foundation;

public final class HashMapRoutesUsage {
    public static void main(String[] args) {
        var map = HashMapRoutes.collisionMap(12);
        System.out.println("碰撞插入后可查询=" + HashMapRoutes.verifyLookups(map, 12));
        HashMapRoutes.growForSplit(map);
        System.out.println(
                "扩容后条目=" + map.size() + "，原键仍可查=" + HashMapRoutes.verifyLookups(map, 12));
    }
}
