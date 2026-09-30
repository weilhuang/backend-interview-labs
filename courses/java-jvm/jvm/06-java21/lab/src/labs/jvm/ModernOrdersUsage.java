package labs.jvm;

public final class ModernOrdersUsage {
    public static void main(String[] args) throws Exception {
        System.out.println(
                "退款变动="
                        + ModernOrders.delta(
                                new ModernOrders.Refund("A", new ModernOrders.Money(40))));
        System.out.println(
                "最新事件="
                        + ModernOrders.newest(
                                new java.util.ArrayList<>(java.util.List.of("A", "B", "C")), 2));
        System.out.println("虚拟线程结果=" + ModernOrders.boundedSquares(java.util.List.of(2, 3), 2));
    }
}
