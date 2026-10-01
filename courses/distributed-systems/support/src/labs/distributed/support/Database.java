package labs.distributed.support;

import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;

/** 每次操作独立连接，课程不把进程锁当作数据库锁。生产应配置有界连接池。 */
public record Database(String url, String user, String password) {
  @FunctionalInterface
  public interface Work<T> {
    T apply(Connection connection) throws SQLException;
  }

  public Connection open() throws SQLException {
    if (url.startsWith("jdbc:mysql:")) {
      java.util.Properties properties = new java.util.Properties();
      properties.setProperty("user", user);
      properties.setProperty("password", password);
      properties.setProperty("connectTimeout", "5000");
      properties.setProperty("socketTimeout", "15000");
      return DriverManager.getConnection(url, properties);
    }
    return DriverManager.getConnection(url, user, password);
  }

  public <T> T transaction(Work<T> work) throws SQLException {
    try (Connection connection = open()) {
      connection.setAutoCommit(false);
      connection.setTransactionIsolation(Connection.TRANSACTION_READ_COMMITTED);
      try {
        T result = work.apply(connection);
        connection.commit();
        return result;
      } catch (SQLException | RuntimeException | Error failure) {
        try {
          connection.rollback();
        } catch (SQLException rollbackFailure) {
          failure.addSuppressed(rollbackFailure);
        }
        throw failure;
      }
    }
  }

  public void execute(String sql, Object... parameters) throws SQLException {
    try (Connection connection = open()) {
      update(connection, sql, parameters);
    }
  }

  public long scalar(String sql, Object... parameters) throws SQLException {
    try (Connection connection = open();
        PreparedStatement statement = prepare(connection, sql, parameters);
        ResultSet rows = statement.executeQuery()) {
      if (!rows.next()) {
        throw new SQLException("预期一行查询结果");
      }
      return rows.getLong(1);
    }
  }

  public static PreparedStatement prepare(Connection connection, String sql, Object... parameters)
      throws SQLException {
    PreparedStatement statement = connection.prepareStatement(sql);
    statement.setQueryTimeout(5);
    for (int i = 0; i < parameters.length; i++) {
      statement.setObject(i + 1, parameters[i]);
    }
    return statement;
  }

  public static int update(Connection connection, String sql, Object... parameters)
      throws SQLException {
    try (PreparedStatement statement = prepare(connection, sql, parameters)) {
      return statement.executeUpdate();
    }
  }

  public static boolean duplicate(SQLException failure) {
    return failure.getErrorCode() == 1062 || "23505".equals(failure.getSQLState());
  }
}
