import static org.junit.jupiter.api.Assertions.*;

import java.util.*;
import labs.Snapshots;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.Timeout;

// Visible sample. Add your own boundary tests here; keep hidden contract checks unchanged.
@Timeout(value = 3, threadMode = Timeout.ThreadMode.SEPARATE_THREAD)
class SnapshotsExamplesTest {
  @Test
  void workedExample() {
    assertEquals(List.of("a"), Snapshots.range(List.of("a", "b"), 0, 1));
  }
}
