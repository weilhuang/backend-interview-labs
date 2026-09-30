package labs;

import java.util.*;

// 完整调用端：先构造输入，再调用业务接口，最后打印可核对的结果。
public final class PaidTotalsUsage {
    private PaidTotalsUsage() {}

    public static void main(String[] args) {
        var orders = List.of(
            new PaidTotals.Order(120, PaidTotals.Status.PAID),
            new PaidTotals.Order(900, PaidTotals.Status.PENDING),
            new PaidTotals.Order(80, PaidTotals.Status.PAID));
        System.out.println("已付款总额（分）=" + PaidTotals.total(orders));
    }
}
