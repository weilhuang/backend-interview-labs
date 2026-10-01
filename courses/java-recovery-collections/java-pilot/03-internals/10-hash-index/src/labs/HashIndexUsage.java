package labs;

import java.util.*;

// 完整调用端：先构造输入，再调用业务接口，最后打印可核对的结果。
public final class HashIndexUsage {
    private HashIndexUsage() {}

    public static void main(String[] args) {
        int rawHash = 0x00010000;
        System.out.println("扰动后=" + HashIndex.spread(rawHash));
        System.out.println("桶索引=" + HashIndex.index(rawHash, 16));
    }
}
