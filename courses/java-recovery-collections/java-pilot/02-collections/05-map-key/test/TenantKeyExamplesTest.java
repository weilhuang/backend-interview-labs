import static org.junit.jupiter.api.Assertions.*;

import java.util.*;
import labs.TenantKey;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.Timeout;

// Visible sample. Add your own boundary tests here; keep hidden contract checks unchanged.
@Timeout(value = 3, threadMode = Timeout.ThreadMode.SEPARATE_THREAD)
class TenantKeyExamplesTest {
  @Test
  void workedExample() {
    assertEquals(new TenantKey("acme", 7), new TenantKey("acme", 7));
  }
}
