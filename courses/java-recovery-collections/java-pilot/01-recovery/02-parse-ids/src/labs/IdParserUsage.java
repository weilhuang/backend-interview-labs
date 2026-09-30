package labs;

import java.util.*;

// 完整调用端：先构造输入，再调用业务接口，最后打印可核对的结果。
public final class IdParserUsage {
    private IdParserUsage() {}

    public static void main(String[] args) {
        List<Integer> ids = IdParser.parse("3, 1,03,2");
        System.out.println("解析后的 ID=" + ids);
    }
}
