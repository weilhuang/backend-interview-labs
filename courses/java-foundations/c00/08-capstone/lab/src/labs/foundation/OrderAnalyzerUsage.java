package labs.foundation;

public final class OrderAnalyzerUsage {
    public static void main(String[] args) {
        System.out.print(
                OrderAnalyzer.analyze(
                        java.util.List.of("A|张三|120|PAID", "B|张三|80|PAID", "A|张三|999|PAID"),
                        Order.Status.PAID));
    }
}
