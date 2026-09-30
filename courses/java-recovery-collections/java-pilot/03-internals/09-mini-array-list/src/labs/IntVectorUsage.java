package labs;

import java.util.*;

// 完整调用端：先构造输入，再调用业务接口，最后打印可核对的结果。
public final class IntVectorUsage {
    private IntVectorUsage() {}

    public static void main(String[] args) {
        var vector = new IntVector();
        for (int i = 1; i <= 5; i++) vector.add(i);
        System.out.println("删除值=" + vector.removeAt(1));
        System.out.println("首项=" + vector.get(0));
        System.out.println("有效元素=" + vector.size());
        System.out.println("容量=" + vector.capacity());
    }
}
