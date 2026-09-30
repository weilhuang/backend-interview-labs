package labs.foundation;

public final class MoneyUsage {
    public static void main(String[] args) {
        System.out.println("银行家舍入=" + Money.of("1.015"));
        System.out.println("订单金额=" + Money.of("10.00").plus(Money.of("2.50")));
    }
}
