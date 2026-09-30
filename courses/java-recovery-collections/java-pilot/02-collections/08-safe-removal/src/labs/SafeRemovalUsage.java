package labs;

import java.util.*;

// 完整调用端：先构造输入，再调用业务接口，最后打印可核对的结果。
public final class SafeRemovalUsage {
    private SafeRemovalUsage() {}

    public static void main(String[] args) {
        var values = new ArrayList<>(List.of(-1, -2, 0, 3, -4));
        int removed = SafeRemoval.removeNegative(values);
        System.out.println("删除数量=" + removed);
        System.out.println("剩余元素=" + values);
    }
}
