package labs.distributed;

import static org.junit.jupiter.api.Assertions.*;

import com.mysql.cj.jdbc.MysqlXADataSource;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Arrays;
import javax.transaction.xa.XAResource;
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
      a = Images.restartAndAwait(first);
      b = Images.restartAndAwait(second);
      // 重建所有XA连接与协调器对象后，按落盘决策完成两个分支。
      var recovered = new XaTransfer(a, b, temporary.resolve("commit.log"));
      assertEquals(2, recovered.recover("xa_commit"));
      assertEquals(70, a.scalar("SELECT balance FROM xa_account"));
      assertEquals(130, b.scalar("SELECT balance FROM xa_account"));
      assertEquals(0, recovered.recover("xa_commit"));

      Path normalJournal = temporary.resolve("normal.log");
      new XaTransfer(a, b, normalJournal).transfer("xa_normal", 20, false, false);
      // 必须先只读检查两个资源；不能调用恢复器修复漏掉的commit，也不能先读被锁余额。
      assertAll(
          () -> assertEquals(0, preparedBranches(Images.database(first), "xa_normal"), "转出分支未完成"),
          () -> assertEquals(0, preparedBranches(Images.database(second), "xa_normal"), "转入分支未完成"));
      assertEquals("COMMIT xa_normal\n", Files.readString(normalJournal));
      assertEquals(50, a.scalar("SELECT balance FROM xa_account"));
      assertEquals(150, b.scalar("SELECT balance FROM xa_account"));
      var normalRecovered = new XaTransfer(a, b, normalJournal);
      assertEquals(0, normalRecovered.recover("xa_normal"));
      assertEquals(0, normalRecovered.recover("xa_normal"));
      assertEquals(50, a.scalar("SELECT balance FROM xa_account"));
      assertEquals(150, b.scalar("SELECT balance FROM xa_account"));
    }
  }

  private static int preparedBranches(Database database, String transaction) throws Exception {
    var source = new MysqlXADataSource();
    source.setUrl(database.url());
    source.setUser(database.user());
    source.setPassword(database.password());
    source.setConnectTimeout(5000);
    source.setSocketTimeout(15000);
    var connection = source.getXAConnection();
    try {
      var resource = connection.getXAResource();
      try {
        return (int)
            Arrays.stream(resource.recover(XAResource.TMSTARTRSCAN))
                .filter(branch -> branch.getFormatId() == 0xC10)
                .filter(
                    branch ->
                        Arrays.equals(
                            branch.getGlobalTransactionId(),
                            transaction.getBytes(StandardCharsets.UTF_8)))
                .count();
      } finally {
        resource.recover(XAResource.TMENDRSCAN);
      }
    } finally {
      connection.close();
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
