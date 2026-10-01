import static org.junit.jupiter.api.Assertions.*;

import java.util.*;
import labs.StableDedup;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.Timeout;

// 可见样例：在这里补充自己的边界测试，同时保留完整契约测试作为回归依据。
@Timeout(value = 3, threadMode = Timeout.ThreadMode.SEPARATE_THREAD)
class StableDedupExamplesTest {
  @Test
  void workedExample() {
    assertEquals(List.of(2, 1), StableDedup.distinct(List.of(2, 1, 2)));
  }
}
