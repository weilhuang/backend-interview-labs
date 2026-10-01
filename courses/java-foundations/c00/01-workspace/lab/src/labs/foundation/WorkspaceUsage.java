package labs.foundation;

public final class WorkspaceUsage {
    public static void main(String[] args) {
        System.out.println(
                "已付款总分="
                        + Workspace.paidTotal(
                                java.util.List.of(new Order("A", "客户甲", 150, Order.Status.PAID))));
        System.out.println("测试运行JDK=" + Runtime.version());
    }
}
