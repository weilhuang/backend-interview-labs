import static org.junit.jupiter.api.Assertions.*;

import java.util.*;
import labs.BoundedStack;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.Timeout;

// Visible sample. Add your own boundary tests here; keep hidden contract checks unchanged.
@Timeout(value = 3, threadMode = Timeout.ThreadMode.SEPARATE_THREAD)
class BoundedStackExamplesTest {
  @Test
  void workedExample() {
    var stack = new BoundedStack<Integer>(2);
    stack.push(7);
    assertEquals(Optional.of(7), stack.peek());
  }
}
