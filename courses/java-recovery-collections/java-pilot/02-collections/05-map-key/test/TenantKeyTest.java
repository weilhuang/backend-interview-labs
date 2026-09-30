import static org.junit.jupiter.api.Assertions.*;

import java.util.*;
import labs.TenantKey;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.Timeout;

@Timeout(value = 3, threadMode = Timeout.ThreadMode.SEPARATE_THREAD)
class TenantKeyTest {
  @Test
  void identityAndHashContract() {
    var a = new TenantKey("acme", 7);
    var b = new TenantKey(new String("acme"), 7);
    var c = new TenantKey("acme", 7);
    assertEquals(a, a);
    assertEquals(a, b);
    assertEquals(b, a);
    assertEquals(b, c);
    assertEquals(a, c);
    assertEquals(a.hashCode(), b.hashCode());
  }

  @Test
  void distinguishesFieldsAndTypes() {
    var a = new TenantKey("acme", 7);
    assertNotEquals(a, new TenantKey("ACME", 7));
    assertNotEquals(a, new TenantKey("acme", 8));
    assertNotEquals(a, null);
    assertNotEquals(a, "acme:7");
  }

  @Test
  void lookupUsesEquivalentInstance() {
    var map = new HashMap<TenantKey, String>();
    map.put(new TenantKey("acme", 7), "ok");
    assertEquals("ok", map.get(new TenantKey("acme", 7)));
    map.put(new TenantKey("acme", 7), "new");
    assertEquals(1, map.size());
  }

  @Test
  void allowsUnequalHashCollision() {
    var a = new TenantKey("Aa", 1);
    var b = new TenantKey("BB", 1);
    assertNotEquals(a, b);
    var map = new HashMap<TenantKey, Integer>();
    map.put(a, 1);
    map.put(b, 2);
    assertEquals(2, map.size());
  }

  @Test
  void validatesAndRetainsIdentity() {
    assertThrows(NullPointerException.class, () -> new TenantKey(null, 1));
    assertThrows(IllegalArgumentException.class, () -> new TenantKey(" ", 1));
    assertThrows(IllegalArgumentException.class, () -> new TenantKey("x", 0));
    var a = new TenantKey(" x ", Long.MAX_VALUE);
    assertEquals(" x ", a.tenant());
    assertEquals(Long.MAX_VALUE, a.userId());
  }
}
