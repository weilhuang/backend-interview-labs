import static org.junit.jupiter.api.Assertions.*;

import java.util.*;
import labs.HashIndex;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.Timeout;

// Visible sample. Add your own boundary tests here; keep hidden contract checks unchanged.
@Timeout(value = 3, threadMode = Timeout.ThreadMode.SEPARATE_THREAD)
class HashIndexExamplesTest {
  @Test
  void workedExample() {
    assertEquals(1, HashIndex.index(0x00010000, 16));
  }
}
