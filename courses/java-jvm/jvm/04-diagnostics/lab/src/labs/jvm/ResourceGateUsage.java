package labs.jvm;

public final class ResourceGateUsage {
    public static void main(String[] args) throws Exception {
        var gate = new ResourceGate(2);
        System.out.println("业务结果=" + gate.call(() -> "订单完成"));
        System.out.println("剩余许可=" + gate.available());
    }
}
