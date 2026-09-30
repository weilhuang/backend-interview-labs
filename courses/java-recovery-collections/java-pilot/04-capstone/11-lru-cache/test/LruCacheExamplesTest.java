import static org.junit.jupiter.api.Assertions.*;

import java.util.*;
import labs.LruCache;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.Timeout;

// Visible sample. Add your own boundary tests here; keep hidden contract checks unchanged.
@Timeout(value = 3, threadMode = Timeout.ThreadMode.SEPARATE_THREAD)
class LruCacheExamplesTest {
  @Test
  void workedExample() {
    var cache = new LruCache<String, Integer>(2);
    cache.put("a", 1);
    assertEquals(Optional.of(1), cache.get("a"));
  }
}
