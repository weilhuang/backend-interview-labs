import static org.junit.jupiter.api.Assertions.*;

import java.util.*;
import labs.HashIndex;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.Timeout;

@Timeout(value = 3, threadMode = Timeout.ThreadMode.SEPARATE_THREAD)
class HashIndexTest {
  @Test
  void mixesHighBitsWithUnsignedShift() {
    assertEquals(0x00010001, HashIndex.spread(0x00010000));
    assertEquals(0x80008000, HashIndex.spread(Integer.MIN_VALUE));
    assertEquals(0xffff0000, HashIndex.spread(-1));
  }

  @Test
  void indexesIncludingNegativeHash() {
    assertEquals(1, HashIndex.index(0x00010000, 16));
    assertEquals(0, HashIndex.index(Integer.MIN_VALUE, 16));
    assertEquals(0, HashIndex.index(-1, 1));
  }

  @Test
  void rejectsInvalidCapacities() {
    for (int c : new int[] {0, -1, 3, 6, Integer.MIN_VALUE})
      assertThrows(IllegalArgumentException.class, () -> HashIndex.index(1, c));
    assertTrue(HashIndex.index(-10, 1 << 30) >= 0);
  }

  @Test
  void maskingAndResizePartitionProperty() {
    var random = new Random(17);
    for (int n = 0; n < 5000; n++) {
      int h = random.nextInt();
      int c = 1 << random.nextInt(20);
      int old = HashIndex.index(h, c);
      int next = HashIndex.index(h, c * 2);
      assertTrue(old >= 0 && old < c);
      assertTrue(next == old || next == old + c);
      assertEquals((HashIndex.spread(h) & c) == 0 ? old : old + c, next);
    }
  }
}
