package labs.foundation;

import java.math.*;
import java.util.*;

public final class Money implements Comparable<Money> {
    private final BigDecimal amount;

    private Money(BigDecimal amount) {
        this.amount = amount;
    }

    public static Money of(String decimal) {
        // 作答开始
        BigDecimal raw = new BigDecimal(Objects.requireNonNull(decimal, "金额文本不能为空"));
        if (raw.signum() < 0) throw new IllegalArgumentException("金额不能为负");
        BigDecimal normalized = raw.setScale(2, RoundingMode.HALF_EVEN);
        normalized.unscaledValue().longValueExact();
        return new Money(normalized);
        // 作答结束
    }

    public Money plus(Money other) {
        return of(amount.add(Objects.requireNonNull(other).amount).toPlainString());
    }

    public Money times(BigDecimal factor) {
        if (Objects.requireNonNull(factor).signum() < 0) throw new IllegalArgumentException("乘数非负");
        return of(amount.multiply(factor).toPlainString());
    }

    public long cents() {
        return amount.unscaledValue().longValueExact();
    }

    @Override
    public int compareTo(Money other) {
        return amount.compareTo(Objects.requireNonNull(other).amount);
    }

    @Override
    public boolean equals(Object other) {
        return other instanceof Money that && amount.equals(that.amount);
    }

    @Override
    public int hashCode() {
        return amount.hashCode();
    }

    @Override
    public String toString() {
        return amount.toPlainString();
    }

    public record OrderId(String value) {
        public OrderId {
            value = Objects.requireNonNull(value, "ID不能为空").strip();
            if (value.isEmpty() || value.length() > 64)
                throw new IllegalArgumentException("ID长度须为1至64");
        }
    }
}
