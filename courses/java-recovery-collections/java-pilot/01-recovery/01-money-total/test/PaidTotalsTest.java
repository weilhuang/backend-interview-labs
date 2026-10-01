import static labs.PaidTotals.Status.*;
import static org.junit.jupiter.api.Assertions.*;

import java.util.*;
import labs.PaidTotals;
import labs.PaidTotals.Order;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.Timeout;

@Timeout(value = 3, threadMode = Timeout.ThreadMode.SEPARATE_THREAD)
class PaidTotalsTest {
  @Test
  void emptyAndUnpaid() {
    assertEquals(0, PaidTotals.total(List.of()));
    assertEquals(0, PaidTotals.total(List.of(new Order(9, PENDING), new Order(7, CANCELLED))));
  }

  @Test
  void addsOnlyPaidAndDoesNotOverflowInt() {
    assertEquals(
        4_000_000_007L,
        PaidTotals.total(
            List.of(
                new Order(2_000_000_000L, PAID),
                new Order(2_000_000_007L, PAID),
                new Order(12, CANCELLED))));
  }

  @Test
  void validatesAllOrdersEvenUnpaid() {
    assertThrows(
        IllegalArgumentException.class, () -> PaidTotals.total(List.of(new Order(-1, CANCELLED))));
    assertThrows(NullPointerException.class, () -> PaidTotals.total(null));
    assertThrows(NullPointerException.class, () -> PaidTotals.total(Arrays.asList((Order) null)));
    assertThrows(NullPointerException.class, () -> PaidTotals.total(List.of(new Order(1, null))));
  }

  @Test
  void longBoundaryAndOverflow() {
    assertEquals(
        Long.MAX_VALUE,
        PaidTotals.total(List.of(new Order(Long.MAX_VALUE, PAID), new Order(0, PAID))));
    assertThrows(
        ArithmeticException.class,
        () -> PaidTotals.total(List.of(new Order(Long.MAX_VALUE, PAID), new Order(1, PAID))));
  }

  @Test
  void inputUnchanged() {
    var a = new ArrayList<>(List.of(new Order(3, PAID)));
    var before = List.copyOf(a);
    PaidTotals.total(a);
    assertEquals(before, a);
  }
}
