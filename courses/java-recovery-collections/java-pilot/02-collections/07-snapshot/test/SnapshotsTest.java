import static org.junit.jupiter.api.Assertions.*;

import java.util.*;
import labs.Snapshots;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.Timeout;

@Timeout(value = 3, threadMode = Timeout.ThreadMode.SEPARATE_THREAD)
class SnapshotsTest {
  @Test
  void halfOpenRange() {
    assertEquals(List.of(2, 3), Snapshots.range(List.of(1, 2, 3, 4), 1, 3));
    assertEquals(List.of(), Snapshots.range(List.of(1), 1, 1));
  }

  @Test
  void independentAfterStructuralAndElementChanges() {
    var input = new ArrayList<>(List.of("a", "b", "c"));
    var result = Snapshots.range(input, 0, 2);
    input.set(0, "x");
    input.clear();
    assertEquals(List.of("a", "b"), result);
  }

  @Test
  void immutableResult() {
    var r = Snapshots.range(List.of(1, 2), 0, 1);
    assertThrows(UnsupportedOperationException.class, () -> r.add(3));
    assertThrows(UnsupportedOperationException.class, () -> r.set(0, 9));
  }

  @Test
  void validatesBoundsAndSelectedNulls() {
    assertThrows(NullPointerException.class, () -> Snapshots.range(null, 0, 0));
    for (int[] b : new int[][] {{-1, 1}, {0, 4}, {2, 1}})
      assertThrows(
          IndexOutOfBoundsException.class, () -> Snapshots.range(List.of(1, 2, 3), b[0], b[1]));
    assertThrows(NullPointerException.class, () -> Snapshots.range(Arrays.asList("a", null), 0, 2));
    assertEquals(List.of("a"), Snapshots.range(Arrays.asList("a", null), 0, 1));
  }

  @Test
  void shallowNotDeepCopy() {
    var box = new ArrayList<>(List.of(1));
    var r = Snapshots.range(List.of(box), 0, 1);
    box.add(2);
    assertSame(box, r.get(0));
    assertEquals(List.of(1, 2), r.get(0));
  }
}
