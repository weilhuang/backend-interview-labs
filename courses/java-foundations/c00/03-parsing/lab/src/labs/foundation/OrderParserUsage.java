package labs.foundation;

public final class OrderParserUsage {
    public static void main(String[] args) {
        System.out.println(OrderParser.parseBatch(java.util.List.of(" A | 张三 | 120 | PAID ")));
        try {
            OrderParser.parse("B|甲|坏金额|PAID", 2);
        } catch (ParseFailure e) {
            System.out.println("预期错误=" + e.getMessage());
        }
    }
}
