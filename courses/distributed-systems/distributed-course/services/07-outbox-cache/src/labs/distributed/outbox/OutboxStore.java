package labs.distributed.outbox;

import java.sql.*;
import labs.distributed.support.Database;

public final class OutboxStore {
  @FunctionalInterface
  public interface Sender {
    void send(Event event) throws Exception;
  }

  @FunctionalInterface
  public interface FailurePoint {
    void afterSend();
  }

  private final Database database;

  public OutboxStore(Database database) {
    this.database = database;
  }

  public void initialize() throws SQLException {
    database.execute(
        "CREATE TABLE IF NOT EXISTS product (sku VARCHAR(40) PRIMARY KEY, available INT NOT NULL,"
            + " revision BIGINT NOT NULL)");
    database.execute(
        "CREATE TABLE IF NOT EXISTS outbox (event_id VARCHAR(64) PRIMARY KEY, sku VARCHAR(40) NOT"
            + " NULL, delta INT NOT NULL, revision BIGINT NOT NULL, available INT NOT NULL,"
            + " published INT NOT NULL)");
    try {
      database.execute("INSERT INTO product VALUES ('book', 10, 0)");
    } catch (SQLException failure) {
      if (!Database.duplicate(failure)) throw failure;
    }
  }

  public Event change(String eventId, String sku, int delta) throws SQLException {
    if (!eventId.matches("[a-zA-Z0-9_-]{1,64}")
        || !sku.matches("[a-zA-Z0-9_-]{1,40}")
        || delta == 0) {
      throw new IllegalArgumentException("事件键、商品和变更量非法");
    }
    return database.transaction(
        connection -> {
          try {
            Database.update(
                connection, "INSERT INTO outbox VALUES (?, ?, ?, 0, 0, 0)", eventId, sku, delta);
          } catch (SQLException failure) {
            if (!Database.duplicate(failure)) throw failure;
            try (var statement =
                    Database.prepare(connection, "SELECT * FROM outbox WHERE event_id=?", eventId);
                var rows = statement.executeQuery()) {
              rows.next();
              if (!sku.equals(rows.getString("sku")) || delta != rows.getInt("delta"))
                throw new IllegalArgumentException("事件键参数冲突");
              return read(rows);
            }
          }
          // 练习区开始
          try (var statement =
                  Database.prepare(
                      connection, "SELECT * FROM product WHERE sku=? FOR UPDATE", sku);
              var rows = statement.executeQuery()) {
            if (!rows.next()) throw new IllegalArgumentException("商品不存在");
            int next = Math.addExact(rows.getInt("available"), delta);
            if (next < 0) throw new IllegalArgumentException("库存不足");
            long version = Math.addExact(rows.getLong("revision"), 1);
            Database.update(
                connection,
                "UPDATE product SET available=?, revision=? WHERE sku=?",
                next,
                version,
                sku);
            Database.update(
                connection,
                "UPDATE outbox SET available=?, revision=? WHERE event_id=?",
                next,
                version,
                eventId);
            return new Event(eventId, sku, version, next);
          }
          // 练习区结束
        });
  }

  private static Event read(ResultSet rows) throws SQLException {
    return new Event(
        rows.getString("event_id"),
        rows.getString("sku"),
        rows.getLong("revision"),
        rows.getInt("available"));
  }

  public boolean publishOne(Sender sender, FailurePoint failurePoint) throws SQLException {
    return database.transaction(
        connection -> {
          try (var statement =
                  Database.prepare(
                      connection,
                      "SELECT * FROM outbox WHERE published=0 ORDER BY revision LIMIT 1 FOR UPDATE"
                          + " SKIP LOCKED");
              var rows = statement.executeQuery()) {
            if (!rows.next()) return false;
            Event event = read(rows);
            // 练习区开始
            try {
              sender.send(event);
            } catch (InterruptedException failure) {
              Thread.currentThread().interrupt();
              throw new SQLException("发布被中断", failure);
            } catch (Exception failure) {
              throw new SQLException("发布未确认，保留outbox等待重试", failure);
            }
            failurePoint.afterSend();
            Database.update(
                connection, "UPDATE outbox SET published=1 WHERE event_id=?", event.id());
            return true;
            // 练习区结束
          }
        });
  }
}
