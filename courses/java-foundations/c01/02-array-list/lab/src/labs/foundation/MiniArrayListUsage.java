package labs.foundation;

public final class MiniArrayListUsage {
    public static void main(String[] args) {
        var values = new MiniArrayList<String>();
        values.add("订单A");
        values.add("订单B");
        System.out.println("删除=" + values.remove(0));
        System.out.println("剩余=" + values.snapshot() + "，容量=" + values.capacity());
    }
}
