import static org.junit.jupiter.api.Assertions.*;

import java.util.*;
import labs.StableDedup;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.Timeout;

@Timeout(value = 3, threadMode = Timeout.ThreadMode.SEPARATE_THREAD)
class StableDedupTest {
  record Collision(int value) {
    public int hashCode() {
      return 1;
    }
  }

  @Test
  void orderNullAndFirstInstance() {
    String a = new String("a"), b = new String("a");
    var r = StableDedup.distinct(Arrays.asList("z", a, null, b, "z", null));
    assertEquals(Arrays.asList("z", "a", null), r);
    assertSame(a, r.get(1));
  }

  @Test
  void hashCollisionIsNotEquality() {
    assertEquals(
        List.of(new Collision(3), new Collision(1)),
        StableDedup.distinct(List.of(new Collision(3), new Collision(1), new Collision(3))));
  }

  @Test
  void independentMutableResult() {
    var input = new ArrayList<>(List.of(2, 1, 2));
    var result = StableDedup.distinct(input);
    result.add(9);
    assertEquals(List.of(2, 1, 2), input);
    input.clear();
    assertEquals(List.of(2, 1, 9), result);
  }

  @Test
  void emptyAndNullList() {
    var a = StableDedup.distinct(List.of());
    a.add("x");
    assertEquals(List.of("x"), a);
    assertThrows(NullPointerException.class, () -> StableDedup.distinct(null));
  }
}
