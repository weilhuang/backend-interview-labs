package labs.distributed.transactions;

import java.sql.*;
import labs.distributed.support.Database;

/** 真实本地事务参与者：不实现生产TCC协调器、自动扫描器或跨地域仲裁。 */
public final class TccInventory {
  private final Database database;

  public TccInventory(Database database) {
    this.database = database;
  }

  public void initialize(int total) throws SQLException {
    if (total < 0) throw new IllegalArgumentException("初始库存不能为负");
    database.execute(
        "CREATE TABLE IF NOT EXISTS tcc_stock (sku VARCHAR(40) PRIMARY KEY, available INT NOT NULL,"
            + " reserved INT NOT NULL, sold INT NOT NULL)");
    database.execute(
        "CREATE TABLE IF NOT EXISTS tcc_branch (branch_id VARCHAR(64) PRIMARY KEY, sku VARCHAR(40),"
            + " quantity INT NOT NULL, state VARCHAR(16) NOT NULL)");
    try {
      database.execute("INSERT INTO tcc_stock VALUES ('book', ?, 0, 0)", total);
    } catch (SQLException failure) {
      if (!Database.duplicate(failure)) throw failure;
    }
  }

  private static void insert(
      Connection connection, String id, String sku, int quantity, String state)
      throws SQLException {
    try {
      Database.update(
          connection, "INSERT INTO tcc_branch VALUES (?, ?, ?, ?)", id, sku, quantity, state);
    } catch (SQLException failure) {
      if (!Database.duplicate(failure)) throw failure;
    }
  }

  public boolean reserve(String id, String sku, int quantity) throws SQLException {
    if (id == null
        || id.isBlank()
        || id.length() > 64
        || sku == null
        || sku.isBlank()
        || quantity < 1) {
      throw new IllegalArgumentException("预留参数非法");
    }
    return database.transaction(
        connection -> {
          insert(connection, id, sku, quantity, "NEW");
          try (var statement =
                  Database.prepare(
                      connection, "SELECT * FROM tcc_branch WHERE branch_id=? FOR UPDATE", id);
              var rows = statement.executeQuery()) {
            rows.next();
            String state = rows.getString("state");
            // 练习区开始
            if (state.equals("CANCELLED")) return false;
            if (!sku.equals(rows.getString("sku")) || quantity != rows.getInt("quantity")) {
              throw new IllegalArgumentException("分支键参数冲突");
            }
            if (state.equals("RESERVED") || state.equals("CONFIRMED")) return true;
            if (Database.update(
                    connection,
                    "UPDATE tcc_stock SET available=available-?, reserved=reserved+? WHERE sku=?"
                        + " AND available>=?",
                    quantity,
                    quantity,
                    sku,
                    quantity)
                == 0) return false;
            Database.update(
                connection, "UPDATE tcc_branch SET state='RESERVED' WHERE branch_id=?", id);
            return true;
            // 练习区结束
          }
        });
  }

  public boolean confirm(String id) throws SQLException {
    return finish(id, true);
  }

  public boolean cancel(String id) throws SQLException {
    return finish(id, false);
  }

  private boolean finish(String id, boolean confirm) throws SQLException {
    if (id == null || id.isBlank() || id.length() > 64) throw new IllegalArgumentException("分支键非法");
    return database.transaction(
        connection -> {
          if (!confirm) insert(connection, id, null, 0, "CANCELLED");
          try (var statement =
                  Database.prepare(
                      connection, "SELECT * FROM tcc_branch WHERE branch_id=? FOR UPDATE", id);
              var rows = statement.executeQuery()) {
            if (!rows.next()) return false;
            String state = rows.getString("state");
            int quantity = rows.getInt("quantity");
            String sku = rows.getString("sku");
            // 练习区开始
            if (confirm && state.equals("CONFIRMED")) return true;
            if (!confirm && state.equals("CANCELLED")) return true;
            if (!confirm && state.equals("NEW")) {
              Database.update(
                  connection, "UPDATE tcc_branch SET state='CANCELLED' WHERE branch_id=?", id);
              return true;
            }
            if (!state.equals("RESERVED")) return false;
            String sql =
                confirm
                    ? "UPDATE tcc_stock SET reserved=reserved-?, sold=sold+? WHERE sku=? AND"
                        + " reserved>=?"
                    : "UPDATE tcc_stock SET reserved=reserved-?, available=available+? WHERE sku=?"
                        + " AND reserved>=?";
            if (Database.update(connection, sql, quantity, quantity, sku, quantity) != 1) {
              throw new IllegalStateException("库存守恒被破坏，禁止静默补偿");
            }
            Database.update(
                connection,
                "UPDATE tcc_branch SET state=? WHERE branch_id=?",
                confirm ? "CONFIRMED" : "CANCELLED",
                id);
            return true;
            // 练习区结束
          }
        });
  }
}
