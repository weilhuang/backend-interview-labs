import static org.junit.jupiter.api.Assertions.*;

import java.util.*;
import labs.StableDedup;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.Timeout;

// Visible sample. Add your own boundary tests here; keep hidden contract checks unchanged.
@Timeout(value = 3, threadMode = Timeout.ThreadMode.SEPARATE_THREAD)
class StableDedupExamplesTest {
  @Test
  void workedExample() {
    assertEquals(List.of(2, 1), StableDedup.distinct(List.of(2, 1, 2)));
  }
}
