package labs.distributed.transactions;

import java.sql.*;
import labs.distributed.support.Database;

/** 可恢复编排：协调日志和两个参与者各自本地事务。单次驱动有界，调度重试由调用方负责。 */
public final class Saga {
  public interface FailurePoint {
    void after(String point);
  }

  private final Database journal;
  private final TccInventory inventory;
  private final PaymentLedger payment;

  public Saga(Database journal, TccInventory inventory, PaymentLedger payment) {
    this.journal = journal;
    this.inventory = inventory;
    this.payment = payment;
  }

  public void initialize() throws SQLException {
    journal.execute(
        "CREATE TABLE IF NOT EXISTS saga_log (saga_id VARCHAR(64) PRIMARY KEY, quantity INT NOT"
            + " NULL, amount INT NOT NULL, state VARCHAR(24) NOT NULL)");
  }

  public void start(String id, int quantity, int amount) throws SQLException {
    if (quantity < 1 || amount < 1) throw new IllegalArgumentException("业务参数必须为正");
    try {
      journal.execute("INSERT INTO saga_log VALUES (?, ?, ?, 'STARTED')", id, quantity, amount);
    } catch (SQLException failure) {
      if (!Database.duplicate(failure)) throw failure;
      try (var connection = journal.open();
          var query =
              Database.prepare(
                  connection, "SELECT quantity, amount FROM saga_log WHERE saga_id=?", id);
          var rows = query.executeQuery()) {
        if (!rows.next() || rows.getInt(1) != quantity || rows.getInt(2) != amount)
          throw new IllegalArgumentException("Saga键参数冲突");
      }
    }
  }

  public String step(String id, FailurePoint failurePoint) throws SQLException {
    // 协调行锁跨越一次有界参与者调用，教学实现选择简单串行化，代价是锁占用。
    return journal.transaction(
        connection -> {
          try (var query =
                  Database.prepare(
                      connection, "SELECT * FROM saga_log WHERE saga_id=? FOR UPDATE", id);
              var rows = query.executeQuery()) {
            if (!rows.next()) throw new IllegalArgumentException("Saga不存在");
            String state = rows.getString("state");
            // 练习区开始
            String next =
                switch (state) {
                  case "STARTED" -> {
                    boolean reserved = inventory.reserve(id, "book", rows.getInt("quantity"));
                    failurePoint.after("库存提交后日志前");
                    yield reserved ? "RESERVED" : "COMPENSATING";
                  }
                  case "RESERVED" -> {
                    boolean charged = payment.charge(id, rows.getInt("amount"));
                    failurePoint.after("支付提交后日志前");
                    yield charged ? "COMPLETED" : "COMPENSATING";
                  }
                  case "COMPENSATING" -> {
                    payment.refund(id);
                    failurePoint.after("退款后库存释放前");
                    if (!inventory.cancel(id))
                      throw new IllegalStateException("库存补偿未完成，必须继续重试或人工核对");
                    yield "CANCELLED";
                  }
                  default -> state;
                };
            Database.update(connection, "UPDATE saga_log SET state=? WHERE saga_id=?", next, id);
            return next;
            // 练习区结束
          }
        });
  }

  public void requestCompensation(String id) throws SQLException {
    // 业务取消也经过协调行锁；已完成订单的退款必须是另一项明确的业务流程。
    journal.execute(
        "UPDATE saga_log SET state='COMPENSATING' WHERE saga_id=? AND state NOT IN"
            + " ('COMPLETED','CANCELLED')",
        id);
  }
}
