package labs;

import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;

class LeasesTest {
  @Test
  void rejectsInvalidLeaseAndTtl() {
    assertThrows(IllegalArgumentException.class, () -> new Leases.Lease("x", ""));
    assertThrows(IllegalArgumentException.class, () -> Leases.acquire(null, "x", 0));
    assertThrows(
        IllegalArgumentException.class, () -> Leases.renew(null, new Leases.Lease("x", "t"), -1));
  }

  @Test
  void tokenIdentityIsNotResourceOrdering() {
    assertNotEquals(new Leases.Lease("same", "old"), new Leases.Lease("same", "new"));
  }
}
