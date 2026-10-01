package labs;

import java.util.*;

// 完整调用端：先构造输入，再调用业务接口，最后打印可核对的结果。
public final class RecentIdsUsage {
    private RecentIdsUsage() {}

    public static void main(String[] args) {
        var window = new RecentIds(2);
        List<Boolean> accepted = new ArrayList<>();
        for (String id : List.of("a", "b", "a", "c", "a")) {
            accepted.add(window.offer(id));
        }
        System.out.println("接受结果=" + accepted);
        System.out.println("最终窗口=" + window.snapshot());
    }
}
