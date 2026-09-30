package labs;

import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;

class ConsistencyTest {
  @Test
  void rollbackFailureCannotHideOriginalFailure() {
    var original = new IllegalArgumentException("首个失败");
    var failure = new java.sql.SQLException("回滚也失败");
    java.sql.Connection connection =
        (java.sql.Connection)
            java.lang.reflect.Proxy.newProxyInstance(
                getClass().getClassLoader(),
                new Class<?>[] {java.sql.Connection.class},
                (proxy, method, args) -> {
                  if (method.getName().equals("rollback")) throw failure;
                  return null;
                });
    labs.support.Transactions.rollback(connection, original);
    assertSame(failure, original.getSuppressed()[0]);
    assertEquals("首个失败", original.getMessage());
  }

  @Test
  void codecPreservesDelimitersUnicodeAndEmptyValues() {
    for (String s : new String[] {"价格|¥19.90", "", "n:"}) {
      var p = new Consistency.Product(7, s);
      assertEquals(p, Consistency.Product.decode(p.encoded()));
    }
  }

  @Test
  void rejectsVersionsThatLoseLuaIntegerPrecision() {
    assertThrows(IllegalArgumentException.class, () -> new Consistency.Product(0, "x"));
    assertThrows(
        IllegalArgumentException.class, () -> new Consistency.Product(9_007_199_254_740_992L, "x"));
  }
}
