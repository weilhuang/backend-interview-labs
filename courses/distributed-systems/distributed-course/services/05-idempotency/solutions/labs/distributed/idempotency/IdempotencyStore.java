package labs.distributed.idempotency;

import java.sql.*;
import java.time.Duration;
import java.util.OptionalInt;
import java.util.UUID;
import labs.distributed.support.Database;

/** 数据库持久化领取、租约和代次。幂等键按租户与业务类型划定作用域，不自动删除。 */
public final class IdempotencyStore {
  public enum Kind {
    OWNED,
    BUSY,
    REPLAY
  }

  public record Request(String key, String sku, int quantity) {
    public Request {
      if (key == null
          || !key.matches("[a-zA-Z0-9:_-]{1,64}")
          || sku == null
          || !sku.matches("[a-zA-Z0-9_-]{1,40}")
          || quantity < 1
          || quantity > 1000) {
        throw new IllegalArgumentException("幂等键、商品编号和数量非法");
      }
    }

    public String fingerprint() {
      return sku + ":" + quantity;
    }
  }

  public record Claim(Kind kind, String owner, long generation, int result) {}

  public interface FailurePoint {
    void afterStockUpdate();
  }

  private final Database database;

  public IdempotencyStore(Database database) {
    this.database = database;
  }

  public void initialize(int available) throws SQLException {
    if (available < 0) throw new IllegalArgumentException("初始库存不能为负");
    database.execute(
        "CREATE TABLE IF NOT EXISTS inventory (sku VARCHAR(40) PRIMARY KEY, available INT NOT"
            + " NULL)");
    database.execute(
        "CREATE TABLE IF NOT EXISTS operations (op_key VARCHAR(64) PRIMARY KEY, fingerprint"
            + " VARCHAR(100) NOT NULL, state VARCHAR(16) NOT NULL, owner VARCHAR(40), generation"
            + " BIGINT NOT NULL, lease_until BIGINT NOT NULL, result INT)");
    try {
      database.execute("INSERT INTO inventory(sku, available) VALUES ('book', ?)", available);
    } catch (SQLException failure) {
      if (!Database.duplicate(failure)) throw failure;
    }
  }

  private static long now(Connection connection) throws SQLException {
    try (var statement = Database.prepare(connection, "SELECT CURRENT_TIMESTAMP(6)");
        var rows = statement.executeQuery()) {
      rows.next();
      return rows.getTimestamp(1).getTime();
    }
  }

  public Claim acquire(Request request, Duration lease) throws SQLException {
    if (lease.isNegative() || lease.toMillis() < 1 || lease.compareTo(Duration.ofMinutes(1)) > 0) {
      throw new IllegalArgumentException("租约必须在1毫秒到1分钟之间");
    }
    String owner = UUID.randomUUID().toString();
    return database.transaction(
        connection -> {
          try {
            Database.update(
                connection,
                "INSERT INTO operations VALUES (?, ?, 'PENDING', NULL, 0, 0, NULL)",
                request.key(),
                request.fingerprint());
          } catch (SQLException failure) {
            if (!Database.duplicate(failure)) throw failure;
          }
          try (var statement =
                  Database.prepare(
                      connection,
                      "SELECT * FROM operations WHERE op_key=? FOR UPDATE",
                      request.key());
              var rows = statement.executeQuery()) {
            rows.next();
            // 练习区开始
            if (!request.fingerprint().equals(rows.getString("fingerprint"))) {
              throw new IllegalArgumentException("同一幂等键不能用于不同参数");
            }
            if (rows.getString("state").equals("COMPLETED")) {
              return new Claim(
                  Kind.REPLAY,
                  rows.getString("owner"),
                  rows.getLong("generation"),
                  rows.getInt("result"));
            }
            long time = now(connection);
            if (rows.getLong("lease_until") > time) {
              return new Claim(Kind.BUSY, rows.getString("owner"), rows.getLong("generation"), 0);
            }
            long generation = rows.getLong("generation") + 1;
            Database.update(
                connection,
                "UPDATE operations SET owner=?, generation=?, lease_until=? WHERE op_key=?",
                owner,
                generation,
                Math.addExact(time, lease.toMillis()),
                request.key());
            return new Claim(Kind.OWNED, owner, generation, 0);
            // 练习区结束
          }
        });
  }

  /** 本地库存更新和幂等结果同一个事务；不能把任意外部HTTP写操作放入此保证。 */
  public int complete(Request request, Claim claim, FailurePoint failurePoint) throws SQLException {
    return database.transaction(
        connection -> {
          try (var statement =
                  Database.prepare(
                      connection,
                      "SELECT * FROM operations WHERE op_key=? FOR UPDATE",
                      request.key());
              var rows = statement.executeQuery()) {
            if (!rows.next() || !request.fingerprint().equals(rows.getString("fingerprint"))) {
              throw new IllegalArgumentException("领取记录不存在或参数冲突");
            }
            // 练习区开始
            if (rows.getString("state").equals("COMPLETED")) return rows.getInt("result");
            if (claim.kind() != Kind.OWNED
                || !claim.owner().equals(rows.getString("owner"))
                || claim.generation() != rows.getLong("generation")
                || rows.getLong("lease_until") <= now(connection)) {
              throw new IllegalStateException("租约过期或已被接管，旧持有者禁止提交");
            }
            int changed =
                Database.update(
                    connection,
                    "UPDATE inventory SET available=available-? WHERE sku=? AND available>=?",
                    request.quantity(),
                    request.sku(),
                    request.quantity());
            int remaining = -1;
            if (changed == 1) {
              try (var stock =
                      Database.prepare(
                          connection,
                          "SELECT available FROM inventory WHERE sku=?",
                          request.sku());
                  var stocks = stock.executeQuery()) {
                stocks.next();
                remaining = stocks.getInt(1);
              }
            }
            failurePoint.afterStockUpdate();
            Database.update(
                connection,
                "UPDATE operations SET state='COMPLETED', result=? WHERE op_key=?",
                remaining,
                request.key());
            return remaining;
            // 练习区结束
          }
        });
  }

  public OptionalInt query(String key) throws SQLException {
    try (var connection = database.open();
        var statement =
            Database.prepare(
                connection,
                "SELECT result FROM operations WHERE op_key=? AND state='COMPLETED'",
                key);
        var rows = statement.executeQuery()) {
      return rows.next() ? OptionalInt.of(rows.getInt(1)) : OptionalInt.empty();
    }
  }
}
