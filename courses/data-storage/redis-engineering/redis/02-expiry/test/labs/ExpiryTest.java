package labs;

import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;

class ExpiryTest {
  @Test
  void rejectsOversizedUtf8BeforeRedis() {
    assertFalse(new Expiry(3).put(null, "c07:test", "中文", 10));
  }

  @Test
  void rejectsInvalidConfiguration() {
    assertThrows(IllegalArgumentException.class, () -> new Expiry(0));
    assertThrows(IllegalArgumentException.class, () -> new Expiry(2).put(null, "x", "a", 0));
  }
}
