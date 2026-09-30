package labs;

import java.util.*;

// 完整调用端：先构造输入，再调用业务接口，最后打印可核对的结果。
public final class BoundedStackUsage {
    private BoundedStackUsage() {}

    public static void main(String[] args) {
        var stack = new BoundedStack<String>(2);
        stack.push("a");
        stack.push("b");
        System.out.println("查看栈顶=" + stack.peek());
        System.out.println("弹出栈顶=" + stack.pop());
        System.out.println("剩余数量=" + stack.size());
    }
}
