import static org.junit.jupiter.api.Assertions.*;

import java.util.*;
import labs.RecentIds;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.Timeout;

// Visible sample. Add your own boundary tests here; keep hidden contract checks unchanged.
@Timeout(value = 3, threadMode = Timeout.ThreadMode.SEPARATE_THREAD)
class RecentIdsExamplesTest {
  @Test
  void workedExample() {
    var window = new RecentIds(2);
    assertTrue(window.offer("a"));
    assertFalse(window.offer("a"));
  }
}
