import static org.junit.jupiter.api.Assertions.*;

import java.util.*;
import labs.IntVector;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.Timeout;

@Timeout(value = 3, threadMode = Timeout.ThreadMode.SEPARATE_THREAD)
class IntVectorTest {
  @Test
  void growthAndValues() {
    var v = new IntVector();
    assertEquals(0, v.capacity());
    for (int i = 0; i < 65; i++) {
      v.add(i);
      assertEquals(i + 1, v.size());
      for (int j = 0; j <= i; j++) assertEquals(j, v.get(j));
    }
    assertEquals(128, v.capacity());
  }

  @Test
  void removeFirstMiddleLastNoShrink() {
    var v = new IntVector();
    for (int x : new int[] {1, 2, 3, 4}) v.add(x);
    assertEquals(2, v.removeAt(1));
    assertEquals(3, v.get(1));
    assertEquals(4, v.removeAt(2));
    assertEquals(1, v.removeAt(0));
    assertEquals(3, v.removeAt(0));
    assertEquals(0, v.size());
    assertEquals(4, v.capacity());
    v.add(9);
    assertEquals(9, v.get(0));
  }

  @Test
  void boundsDoNotMutate() {
    var v = new IntVector();
    assertThrows(IndexOutOfBoundsException.class, () -> v.get(0));
    v.add(1);
    assertThrows(IndexOutOfBoundsException.class, () -> v.removeAt(1));
    assertThrows(IndexOutOfBoundsException.class, () -> v.removeAt(-1));
    assertEquals(1, v.size());
    assertEquals(1, v.get(0));
  }

  @Test
  void randomizedAgainstArrayList() {
    var random = new Random(20260930L);
    var v = new IntVector();
    var expected = new ArrayList<Integer>();
    for (int n = 0; n < 1200; n++) {
      if (expected.isEmpty() || random.nextBoolean()) {
        int x = random.nextInt();
        expected.add(x);
        v.add(x);
      } else {
        int i = random.nextInt(expected.size());
        assertEquals(expected.remove(i).intValue(), v.removeAt(i));
      }
      assertEquals(expected.size(), v.size());
      for (int i = 0; i < expected.size(); i++) assertEquals(expected.get(i).intValue(), v.get(i));
    }
  }
}
