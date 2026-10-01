import static org.junit.jupiter.api.Assertions.*;

import java.util.*;
import labs.BoundedStack;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.Timeout;

@Timeout(value = 3, threadMode = Timeout.ThreadMode.SEPARATE_THREAD)
class BoundedStackTest {
  @Test
  void lifoAndPeekDoesNotRemove() {
    var s = new BoundedStack<String>(2);
    s.push("a");
    s.push("b");
    assertEquals(Optional.of("b"), s.peek());
    assertEquals(2, s.size());
    assertEquals(Optional.of("b"), s.pop());
    assertEquals(Optional.of("a"), s.pop());
    assertEquals(Optional.empty(), s.pop());
    assertEquals(Optional.empty(), s.peek());
  }

  @Test
  void overflowKeepsExistingState() {
    var s = new BoundedStack<Integer>(1);
    s.push(7);
    assertThrows(IllegalStateException.class, () -> s.push(8));
    assertEquals(1, s.size());
    assertEquals(Optional.of(7), s.pop());
    s.push(9);
    assertEquals(Optional.of(9), s.peek());
  }

  @Test
  void invalidCapacityAndNull() {
    assertThrows(IllegalArgumentException.class, () -> new BoundedStack<>(0));
    assertThrows(IllegalArgumentException.class, () -> new BoundedStack<>(-1));
    var s = new BoundedStack<>(1);
    assertThrows(NullPointerException.class, () -> s.push(null));
    assertEquals(0, s.size());
    s.push("x");
    assertThrows(NullPointerException.class, () -> s.push(null));
  }

  @Test
  void acceptsUserTypes() {
    record Token(int n) {}
    var s = new BoundedStack<Token>(1);
    s.push(new Token(4));
    assertEquals(new Token(4), s.pop().orElseThrow());
  }
}
