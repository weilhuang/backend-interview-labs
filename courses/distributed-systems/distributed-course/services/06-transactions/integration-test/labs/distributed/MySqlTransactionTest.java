package labs.distributed;

import static org.junit.jupiter.api.Assertions.*;

import java.nio.file.Path;
import labs.distributed.support.*;
import labs.distributed.transactions.*;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class MySqlTransactionTest {
  @TempDir Path temporary;

  @Test
  void 两个MySQL资源准备后无决策回滚有决策提交() throws Exception {
    try (var first = Images.mysql().withUsername("root");
        var second = Images.mysql().withUsername("root")) {
      first.start();
      second.start();
      var a = Images.database(first);
      var b = Images.database(second);
      for (var db : java.util.List.of(a, b)) {
        db.execute("CREATE TABLE xa_account (id INT PRIMARY KEY, balance INT NOT NULL)");
        db.execute("INSERT INTO xa_account VALUES (1, 100)");
      }
      var aborted = new XaTransfer(a, b, temporary.resolve("abort.log"));
      aborted.transfer("xa_abort", 30, true, false);
      assertEquals(2, new XaTransfer(a, b, temporary.resolve("abort.log")).recover("xa_abort"));
      assertEquals(100, a.scalar("SELECT balance FROM xa_account"));
      assertEquals(100, b.scalar("SELECT balance FROM xa_account"));
      var committed = new XaTransfer(a, b, temporary.resolve("commit.log"));
      committed.transfer("xa_commit", 30, false, true);
      // 真实重启两个数据库进程，PREPARED分支必须仍可恢复。
      Images.restartAndAwait(first);
      Images.restartAndAwait(second);
      // 重建所有XA连接与协调器对象后，按落盘决策完成两个分支。
      assertEquals(2, new XaTransfer(a, b, temporary.resolve("commit.log")).recover("xa_commit"));
      assertEquals(70, a.scalar("SELECT balance FROM xa_account"));
      assertEquals(130, b.scalar("SELECT balance FROM xa_account"));
      assertEquals(0, committed.recover("xa_commit"));
    }
  }

  @Test
  void TCC与Saga参与者跨数据库持久化恢复() throws Exception {
    try (var first = Images.mysql();
        var second = Images.mysql()) {
      first.start();
      second.start();
      var a = Images.database(first);
      var b = Images.database(second);
      var stock = new TccInventory(a);
      stock.initialize(10);
      var payment = new PaymentLedger(b);
      payment.initialize(100);
      var saga = new Saga(a, stock, payment);
      saga.initialize();
      saga.start("saga1", 2, 30);
      assertEquals("RESERVED", saga.step("saga1", point -> {}));
      assertThrows(
          IllegalStateException.class,
          () ->
              saga.step(
                  "saga1",
                  point -> {
                    throw new IllegalStateException("支付确认丢失");
                  }));
      assertEquals(70, b.scalar("SELECT credit FROM wallet"));
      var restarted = new Saga(a, new TccInventory(a), new PaymentLedger(b));
      assertEquals("COMPLETED", restarted.step("saga1", point -> {}));
      assertEquals(70, b.scalar("SELECT credit FROM wallet"));
      assertEquals(8, a.scalar("SELECT available FROM tcc_stock"));
    }
  }
}
