import static org.junit.jupiter.api.Assertions.*;

import java.util.*;
import labs.LruCache;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.Timeout;

@Timeout(value = 3, threadMode = Timeout.ThreadMode.SEPARATE_THREAD)
class LruCacheTest {
  @Test
  void readRefreshesAndEvictsLeastRecent() {
    var c = new LruCache<String, Integer>(2);
    c.put("a", 1);
    c.put("b", 2);
    assertEquals(Optional.of(1), c.get("a"));
    c.put("c", 3);
    assertEquals(Optional.empty(), c.get("b"));
    assertEquals(List.of("a", "c"), c.keysLeastToMostRecent());
  }

  @Test
  void overwriteRefreshesWithoutGrowing() {
    var c = new LruCache<String, Integer>(2);
    c.put("a", 1);
    c.put("b", 2);
    c.put("a", 9);
    assertEquals(2, c.size());
    assertEquals(List.of("b", "a"), c.keysLeastToMostRecent());
    c.put("c", 3);
    assertEquals(Optional.of(9), c.get("a"));
    assertEquals(Optional.empty(), c.get("b"));
  }

  @Test
  void missDoesNotChangeOrderAndSnapshotDetached() {
    var c = new LruCache<String, Integer>(2);
    c.put("a", 1);
    c.put("b", 2);
    var snapshot = c.keysLeastToMostRecent();
    assertEquals(Optional.empty(), c.get("x"));
    assertEquals(snapshot, c.keysLeastToMostRecent());
    c.get("a");
    assertEquals(List.of("a", "b"), snapshot);
    assertThrows(UnsupportedOperationException.class, () -> snapshot.add("x"));
  }

  @Test
  void capacityOneAndValidationAtomicity() {
    assertThrows(IllegalArgumentException.class, () -> new LruCache<>(0));
    var c = new LruCache<String, Integer>(1);
    c.put("a", 1);
    assertThrows(NullPointerException.class, () -> c.put("b", null));
    assertThrows(NullPointerException.class, () -> c.put(null, 1));
    assertThrows(NullPointerException.class, () -> c.get(null));
    assertEquals(List.of("a"), c.keysLeastToMostRecent());
    c.put("b", 2);
    assertEquals(List.of("b"), c.keysLeastToMostRecent());
  }
}
