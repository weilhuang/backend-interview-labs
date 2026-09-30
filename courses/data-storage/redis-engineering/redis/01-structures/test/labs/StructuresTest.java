package labs;

import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;

class StructuresTest {
  @Test
  void rejectsNonPositiveTtlBeforeConnecting() {
    assertThrows(
        IllegalArgumentException.class, () -> Structures.incrementWithTtl(null, "c07:test", 0));
    assertThrows(
        IllegalArgumentException.class, () -> Structures.incrementWithTtl(null, "c07:test", -1));
    assertThrows(
        IllegalArgumentException.class,
        () -> Structures.incrementWithTtl(null, "c07:test", Long.MAX_VALUE));
  }
}
