import static org.junit.jupiter.api.Assertions.*;

import java.util.*;
import labs.SafeRemoval;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.Timeout;

@Timeout(value = 3, threadMode = Timeout.ThreadMode.SEPARATE_THREAD)
class SafeRemovalTest {
  @Test
  void removesAdjacentAndEdgesInArrayList() {
    var a = new ArrayList<>(List.of(-1, -2, 0, 3, -4));
    assertEquals(3, SafeRemoval.removeNegative(a));
    assertEquals(List.of(0, 3), a);
  }

  @Test
  void worksForLinkedList() {
    List<Integer> a = new LinkedList<>(List.of(1, -1, 2, -2, -3));
    assertEquals(3, SafeRemoval.removeNegative(a));
    assertEquals(List.of(1, 2), a);
  }

  @Test
  void emptyAllNegativeAndNone() {
    var a = new ArrayList<Integer>();
    assertEquals(0, SafeRemoval.removeNegative(a));
    a.addAll(List.of(-1, -1));
    assertEquals(2, SafeRemoval.removeNegative(a));
    assertTrue(a.isEmpty());
    a.addAll(List.of(0, 1));
    assertEquals(0, SafeRemoval.removeNegative(a));
    assertEquals(List.of(0, 1), a);
  }

  @Test
  void nullValidationBeforeMutation() {
    var a = new ArrayList<>(Arrays.asList(-1, null, 2));
    assertThrows(NullPointerException.class, () -> SafeRemoval.removeNegative(a));
    assertEquals(Arrays.asList(-1, null, 2), a);
    assertThrows(NullPointerException.class, () -> SafeRemoval.removeNegative(null));
  }
}
