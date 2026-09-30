import static org.junit.jupiter.api.Assertions.*;

import java.util.*;
import labs.LruCache;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.Timeout;

// 可见样例：在这里补充自己的边界测试，同时保留完整契约测试作为回归依据。
@Timeout(value = 3, threadMode = Timeout.ThreadMode.SEPARATE_THREAD)
class LruCacheExamplesTest {
  @Test
  void workedExample() {
    var cache = new LruCache<String, Integer>(2);
    cache.put("a", 1);
    assertEquals(Optional.of(1), cache.get("a"));
  }
}
