package labs;

import java.util.*;

// 完整调用端：先构造输入，再调用业务接口，最后打印可核对的结果。
public final class LruCacheUsage {
    private LruCacheUsage() {}

    public static void main(String[] args) {
        var cache = new LruCache<String, Integer>(2);
        cache.put("a", 1);
        cache.put("b", 2);
        cache.get("a");
        cache.put("c", 3);
        System.out.println("从最旧到最新=" + cache.keysLeastToMostRecent());
        System.out.println("读取已淘汰键=" + cache.get("b"));
    }
}
