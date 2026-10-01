import static org.junit.jupiter.api.Assertions.*;

import labs.foundation.*;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.Timeout;

import java.util.*;
import java.util.concurrent.*;

@Timeout(5)
class MoneyTest {
    @Test
    void canonicalEqualityAndRounding() {
        assertEquals(Money.of("1"), Money.of("1.00"));
        assertEquals(Money.of("1.0").hashCode(), Money.of("1.00").hashCode());
        assertEquals(100, Money.of("1.005").cents());
        assertEquals(102, Money.of("1.015").cents());
        assertEquals("0.00", Money.of("0").toString());
        assertEquals(0, Money.of("2.0").compareTo(Money.of("2.00")));
    }

    @Test
    void arithmeticAndBounds() {
        assertEquals("3.25", Money.of("1.20").plus(Money.of("2.05")).toString());
        assertEquals("0.60", Money.of("1.20").times(new java.math.BigDecimal("0.5")).toString());
        assertThrows(IllegalArgumentException.class, () -> Money.of("-0.001"));
        assertThrows(ArithmeticException.class, () -> Money.of("92233720368547758.08"));
        assertThrows(NullPointerException.class, () -> Money.of(null));
        assertThrows(NumberFormatException.class, () -> Money.of("非法"));
    }

    @Test
    void identityAndValues() {
        assertEquals(new Money.OrderId(" A "), new Money.OrderId("A"));
        assertThrows(IllegalArgumentException.class, () -> new Money.OrderId(" "));
        String a = new String("订单"), b = new String("订单");
        assertNotSame(a, b);
        assertEquals(a, b);
        Integer boxed = 1000;
        assertEquals(1000, boxed.intValue());
        Integer absent = null;
        assertThrows(
                NullPointerException.class,
                () -> {
                    int ignored = absent;
                });
        assertNotEquals(new java.math.BigDecimal("1.0"), new java.math.BigDecimal("1.00"));
    }
}
