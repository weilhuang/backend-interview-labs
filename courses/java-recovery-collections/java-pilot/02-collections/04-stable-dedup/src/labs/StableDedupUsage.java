package labs;

import java.util.*;

// 完整调用端：先构造输入，再调用业务接口，最后打印可核对的结果。
public final class StableDedupUsage {
    private StableDedupUsage() {}

    public static void main(String[] args) {
        List<String> values = Arrays.asList("z", "a", null, "a", "z");
        System.out.println("去重结果=" + StableDedup.distinct(values));
        System.out.println("原始列表=" + values);
    }
}
