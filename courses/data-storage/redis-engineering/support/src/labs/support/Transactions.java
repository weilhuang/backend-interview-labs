package labs.support;

import java.sql.Connection;
import java.sql.SQLException;

/** 回滚失败保留为附加异常，不能覆盖最初业务/SQL失败。 */
public final class Transactions {
  private Transactions() {}

  public static void rollback(Connection connection, Throwable original) {
    try {
      connection.rollback();
    } catch (SQLException rollbackFailure) {
      original.addSuppressed(rollbackFailure);
    }
  }
}
