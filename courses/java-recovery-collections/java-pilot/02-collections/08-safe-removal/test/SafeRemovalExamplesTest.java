import static org.junit.jupiter.api.Assertions.*;

import java.util.*;
import labs.SafeRemoval;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.Timeout;

// Visible sample. Add your own boundary tests here; keep hidden contract checks unchanged.
@Timeout(value = 3, threadMode = Timeout.ThreadMode.SEPARATE_THREAD)
class SafeRemovalExamplesTest {
  @Test
  void workedExample() {
    var input = new ArrayList<>(List.of(-1, 0));
    assertEquals(1, SafeRemoval.removeNegative(input));
    assertEquals(List.of(0), input);
  }
}
