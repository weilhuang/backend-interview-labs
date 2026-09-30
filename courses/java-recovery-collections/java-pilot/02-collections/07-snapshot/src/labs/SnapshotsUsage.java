package labs;

import java.util.*;

// 完整调用端：先构造输入，再调用业务接口，最后打印可核对的结果。
public final class SnapshotsUsage {
    private SnapshotsUsage() {}

    public static void main(String[] args) {
        var original = new ArrayList<>(List.of("a", "b", "c"));
        List<String> snapshot = Snapshots.range(original, 0, 2);
        original.set(0, "x");
        original.clear();
        System.out.println("原列表=" + original);
        System.out.println("结构快照=" + snapshot);
    }
}
