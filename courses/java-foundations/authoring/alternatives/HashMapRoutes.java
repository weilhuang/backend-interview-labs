package labs.foundation;

import java.util.*;

public final class HashMapRoutes {
    private HashMapRoutes() {}

    public record Key(int id, int forcedHash) {
        @Override
        public int hashCode() {
            return forcedHash;
        }
    }

    public static Map<Key, Integer> collisionMap(int count) {
        // 作答开始
        if (count < 0 || count > 256) throw new IllegalArgumentException("碰撞样本须为0至256");
        Map<Key, Integer> map = new HashMap<>(16);
        int i = 0;
        while (i < count) {
            map.put(new Key(i, (i % 2) * 64), i);
            i++;
        }
        return map;
        // 作答结束
    }

    public static boolean verifyLookups(Map<Key, Integer> map, int count) {
        for (int i = 0; i < count; i++)
            if (!Objects.equals(i, map.get(new Key(i, (i % 2) * 64)))) return false;
        return true;
    }

    public static Map<Key, Integer> growForSplit(Map<Key, Integer> map) {
        for (int i = 12; i < 60; i++) map.put(new Key(i, i + 1), i);
        return map;
    }
}
