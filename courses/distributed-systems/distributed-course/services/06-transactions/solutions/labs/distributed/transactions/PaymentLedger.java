package labs.distributed.transactions;

import java.sql.*;
import labs.distributed.support.Database;

/** 支付教学账本只使用隔离积分，不连接真实支付商。 */
public final class PaymentLedger {
  private final Database database;

  public PaymentLedger(Database database) {
    this.database = database;
  }

  public void initialize(int credit) throws SQLException {
    if (credit < 0) throw new IllegalArgumentException("初始积分不能为负");
    database.execute("CREATE TABLE IF NOT EXISTS wallet (id INT PRIMARY KEY, credit INT NOT NULL)");
    database.execute(
        "CREATE TABLE IF NOT EXISTS payment (payment_id VARCHAR(64) PRIMARY KEY, amount INT NOT"
            + " NULL, state VARCHAR(16) NOT NULL)");
    try {
      database.execute("INSERT INTO wallet VALUES (1, ?)", credit);
    } catch (SQLException failure) {
      if (!Database.duplicate(failure)) throw failure;
    }
  }

  public boolean charge(String id, int amount) throws SQLException {
    if (amount < 1) throw new IllegalArgumentException("金额必须为正");
    return database.transaction(
        connection -> {
          try {
            Database.update(connection, "INSERT INTO payment VALUES (?, ?, 'NEW')", id, amount);
          } catch (SQLException failure) {
            if (!Database.duplicate(failure)) throw failure;
          }
          try (var statement =
                  Database.prepare(
                      connection, "SELECT * FROM payment WHERE payment_id=? FOR UPDATE", id);
              var rows = statement.executeQuery()) {
            rows.next();
            String state = rows.getString("state");
            if (state.equals("REFUNDED")) return false;
            if (rows.getInt("amount") != amount) throw new IllegalArgumentException("支付幂等键金额冲突");
            if (state.equals("CHARGED")) return true;
            if (Database.update(
                    connection,
                    "UPDATE wallet SET credit=credit-? WHERE id=1 AND credit>=?",
                    amount,
                    amount)
                == 0) return false;
            Database.update(
                connection, "UPDATE payment SET state='CHARGED' WHERE payment_id=?", id);
            return true;
          }
        });
  }

  public void refund(String id) throws SQLException {
    database.transaction(
        connection -> {
          try {
            Database.update(connection, "INSERT INTO payment VALUES (?, 0, 'REFUNDED')", id);
          } catch (SQLException failure) {
            if (!Database.duplicate(failure)) throw failure;
          }
          try (var statement =
                  Database.prepare(
                      connection, "SELECT * FROM payment WHERE payment_id=? FOR UPDATE", id);
              var rows = statement.executeQuery()) {
            rows.next();
            if (rows.getString("state").equals("CHARGED")) {
              Database.update(
                  connection,
                  "UPDATE wallet SET credit=credit+? WHERE id=1",
                  rows.getInt("amount"));
            }
            Database.update(
                connection, "UPDATE payment SET state='REFUNDED' WHERE payment_id=?", id);
            return null;
          }
        });
  }
}
