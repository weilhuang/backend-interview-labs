package labs.foundation;

import java.util.Objects;

public record Order(String id, String customer, long cents, Status status) {
    public enum Status {
        PAID,
        PENDING
    }

    public Order {
        Objects.requireNonNull(id, "订单ID不能为空");
        Objects.requireNonNull(customer, "客户不能为空");
        Objects.requireNonNull(status, "状态不能为空");
        if (id.isBlank() || customer.isBlank() || cents < 0)
            throw new IllegalArgumentException("ID/客户非空，金额非负");
    }
}
