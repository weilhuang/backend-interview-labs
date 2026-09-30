package labs.distributed.outbox;

import java.sql.*;
import labs.distributed.support.Database;

public final class Projector {
  private final Database database;

  public Projector(Database database) {
    this.database = database;
  }

  public void initialize() throws SQLException {
    database.execute(
        "CREATE TABLE IF NOT EXISTS inbox (event_id VARCHAR(64) PRIMARY KEY, fingerprint"
            + " VARCHAR(200) NOT NULL)");
    database.execute(
        "CREATE TABLE IF NOT EXISTS read_model (sku VARCHAR(40) PRIMARY KEY, revision BIGINT NOT"
            + " NULL, available INT NOT NULL)");
  }

  public boolean apply(Event event, Runnable beforeCommit) throws SQLException {
    return database.transaction(
        connection -> {
          // 练习区开始
          try {
            Database.update(
                connection, "INSERT INTO inbox VALUES (?, ?)", event.id(), event.encode());
          } catch (SQLException failure) {
            if (!Database.duplicate(failure)) throw failure;
            try (var statement =
                    Database.prepare(
                        connection, "SELECT fingerprint FROM inbox WHERE event_id=?", event.id());
                var rows = statement.executeQuery()) {
              rows.next();
              if (!event.encode().equals(rows.getString(1)))
                throw new IllegalArgumentException("相同事件ID的载荷冲突");
            }
            return false;
          }
          try {
            Database.update(connection, "INSERT INTO read_model VALUES (?, 0, 0)", event.sku());
          } catch (SQLException failure) {
            if (!Database.duplicate(failure)) throw failure;
          }
          Database.update(
              connection,
              "UPDATE read_model SET revision=?, available=? WHERE sku=? AND revision<?",
              event.version(),
              event.available(),
              event.sku(),
              event.version());
          beforeCommit.run();
          return true;
          // 练习区结束
        });
  }
}
