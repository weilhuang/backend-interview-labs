package labs.jvm;

public final class BoundedStoreUsage {
    public static void main(String[] args) {
        try (var s = new BoundedStore(4)) {
            s.put("订单", new byte[] {1, 2});
            System.out.println("保留字节=" + s.retainedBytes());
            s.remove("订单");
            System.out.println("释放业务引用后=" + s.retainedBytes());
        }
    }
}
