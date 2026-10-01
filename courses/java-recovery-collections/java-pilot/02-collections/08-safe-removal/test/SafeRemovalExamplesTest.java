import static org.junit.jupiter.api.Assertions.*;

import java.util.*;
import labs.SafeRemoval;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.Timeout;

// 可见样例：在这里补充自己的边界测试，同时保留完整契约测试作为回归依据。
@Timeout(value = 3, threadMode = Timeout.ThreadMode.SEPARATE_THREAD)
class SafeRemovalExamplesTest {
  @Test
  void workedExample() {
    var input = new ArrayList<>(List.of(-1, 0));
    assertEquals(1, SafeRemoval.removeNegative(input));
    assertEquals(List.of(0), input);
  }
}
