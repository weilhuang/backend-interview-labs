package labs;

public final class BoundedBuffersUsage {
    public static void main(String[] args) throws Exception {
        for (BoundedBuffers.Buffer<String> b :
                java.util.List.<BoundedBuffers.Buffer<String>>of(
                        new BoundedBuffers.MonitorBuffer<>(2),
                        new BoundedBuffers.LockBuffer<>(2))) {
            b.put("订单-1");
            b.put("订单-2");
            b.close();
            for (var value = b.take(); value.isPresent(); value = b.take())
                System.out.println(value.get());
            System.out.println("已排空且关闭");
        }
    }
}
