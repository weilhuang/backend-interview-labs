package labs;

import java.util.*;

// 完整调用端：先构造输入，再调用业务接口，最后打印可核对的结果。
public final class TopWordsUsage {
    private TopWordsUsage() {}

    public static void main(String[] args) {
        List<String> tokens = List.of("b", "A", "b", "c", "a", " ");
        for (TopWords.Count item : TopWords.top(tokens, 2)) {
            System.out.println("词=" + item.word() + "，次数=" + item.count());
        }
    }
}
