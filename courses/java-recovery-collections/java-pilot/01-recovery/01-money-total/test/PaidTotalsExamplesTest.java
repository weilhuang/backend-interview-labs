import static org.junit.jupiter.api.Assertions.*;

import java.util.*;
import labs.PaidTotals;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.Timeout;

// Visible sample. Add your own boundary tests here; keep hidden contract checks unchanged.
@Timeout(value = 3, threadMode = Timeout.ThreadMode.SEPARATE_THREAD)
class PaidTotalsExamplesTest {
  @Test
  void workedExample() {
    assertEquals(5, PaidTotals.total(List.of(new PaidTotals.Order(5, PaidTotals.Status.PAID))));
  }
}
