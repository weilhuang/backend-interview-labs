package labs.foundation;

public final class DebugRepairsUsage {
    public static void main(String[] args) throws Exception {
        System.out.println("半开区间=" + DebugRepairs.slice(java.util.List.of("A", "B"), 1, 2));
        System.out.println(
                "资源执行=" + DebugRepairs.withResource(() -> System.out.println("资源关闭"), () -> "完成"));
    }
}
