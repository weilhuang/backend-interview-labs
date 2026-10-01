public class ScopedDemo {
    static final ScopedValue<String> TENANT = ScopedValue.newInstance();

    public static void main(String[] args) {
        ScopedValue.where(TENANT, "实验租户").run(() -> System.out.println(TENANT.get()));
        if (TENANT.isBound()) {
            throw new AssertionError("作用域结束后不应绑定");
        }
    }
}
