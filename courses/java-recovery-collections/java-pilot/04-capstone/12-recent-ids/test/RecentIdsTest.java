import static org.junit.jupiter.api.Assertions.*;

import java.util.*;
import labs.RecentIds;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.Timeout;

@Timeout(value = 3, threadMode = Timeout.ThreadMode.SEPARATE_THREAD)
class RecentIdsTest {
  @Test
  void duplicateDoesNotRefreshAndEvictedCanReturn() {
    var w = new RecentIds(2);
    assertTrue(w.offer("a"));
    assertTrue(w.offer("b"));
    assertFalse(w.offer("a"));
    assertTrue(w.offer("c"));
    assertEquals(List.of("b", "c"), w.snapshot());
    assertTrue(w.offer("a"));
    assertEquals(List.of("c", "a"), w.snapshot());
  }

  @Test
  void snapshotsAndFailureAtomicity() {
    var w = new RecentIds(1);
    w.offer(" x ");
    var s = w.snapshot();
    assertThrows(NullPointerException.class, () -> w.offer(null));
    assertThrows(IllegalArgumentException.class, () -> w.offer(" 	"));
    assertEquals(List.of(" x "), w.snapshot());
    w.offer("x");
    assertEquals(List.of(" x "), s);
    assertThrows(UnsupportedOperationException.class, () -> s.add("z"));
  }

  @Test
  void validatesCapacity() {
    assertThrows(IllegalArgumentException.class, () -> new RecentIds(0));
    assertThrows(IllegalArgumentException.class, () -> new RecentIds(-1));
  }

  @Test
  void randomizedAgainstSimpleOracle() {
    var r = new Random(42);
    for (int capacity : new int[] {1, 2, 7, 20}) {
      var w = new RecentIds(capacity);
      var oracle = new ArrayList<String>();
      for (int n = 0; n < 1000; n++) {
        String id = "id" + r.nextInt(31);
        boolean expected = !oracle.contains(id);
        if (expected) {
          if (oracle.size() == capacity) oracle.remove(0);
          oracle.add(id);
        }
        assertEquals(expected, w.offer(id));
        assertEquals(oracle, w.snapshot());
      }
    }
  }
}
