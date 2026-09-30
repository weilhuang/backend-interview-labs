package labs.distributed;

import static org.junit.jupiter.api.Assertions.*;

import java.sql.Connection;
import java.sql.SQLException;
import java.sql.SQLTransactionRollbackException;
import java.util.HashSet;
import java.util.UUID;
import java.util.concurrent.atomic.AtomicInteger;
import labs.distributed.idempotency.TransactionRetry;
import labs.distributed.support.Database;
import org.junit.jupiter.api.Test;

/** 注入SQL异常验证重试控制与真实H2回滚；不能替代MySQL真实锁集成。 */
class TransactionRetryTest {
  Database database() throws SQLException {
    var db = new Database("jdbc:h2:mem:" + UUID.randomUUID() + ";DB_CLOSE_DELAY=-1", "sa", "");
    db.execute("CREATE TABLE stock(available INT)");
    db.execute("INSERT INTO stock VALUES(10)");
    return db;
  }

  SQLException deadlock() {
    return new SQLTransactionRollbackException("注入整个事务已回滚的死锁", "40001", 1213);
  }

  @Test
  void 重试必须回滚后重新打开连接并重放完整事务() throws Exception {
    var db = database();
    var attempts = new AtomicInteger();
    var connections = new HashSet<Connection>();
    int result =
        new TransactionRetry(4, delay -> {})
            .run(
                db,
                connection -> {
                  connections.add(connection);
                  Database.update(connection, "UPDATE stock SET available=available-2");
                  if (attempts.incrementAndGet() == 1) throw deadlock();
                  return 8;
                });
    assertEquals(8, result);
    assertEquals(2, connections.size());
    assertTrue(
        connections.stream()
            .allMatch(
                connection -> {
                  try {
                    return connection.isClosed();
                  } catch (SQLException failure) {
                    throw new AssertionError(failure);
                  }
                }));
    assertEquals(8, db.scalar("SELECT available FROM stock"));
  }

  @Test
  void 持续死锁达到上限后抛出原错误而非伪成功() throws Exception {
    var db = database();
    var attempts = new AtomicInteger();
    var sleeps = new AtomicInteger();
    SQLException last = deadlock();
    SQLException failure =
        assertThrows(
            SQLException.class,
            () ->
                new TransactionRetry(
                        4,
                        delay -> {
                          assertTrue(delay.toMillis() <= 20);
                          sleeps.incrementAndGet();
                        })
                    .run(
                        db,
                        connection -> {
                          attempts.incrementAndGet();
                          Database.update(connection, "UPDATE stock SET available=available-1");
                          throw last;
                        }));
    assertSame(last, failure);
    assertEquals(4, attempts.get());
    assertEquals(3, sleeps.get());
    assertEquals(10, db.scalar("SELECT available FROM stock"));
  }

  @Test
  void 提交结果未知及回滚不确定和普通SQL错误都禁止重试() throws Exception {
    var db = database();
    var uncertainRollback = deadlock();
    uncertainRollback.addSuppressed(new SQLException("回滚连接中断", "08006"));
    for (SQLException error :
        java.util.List.of(
            new SQLException("COMMIT响应丢失", "08006"),
            new SQLException("锁等待超时", "HY000", 1205),
            new SQLException("重复键", "23000", 1062),
            uncertainRollback)) {
      var attempts = new AtomicInteger();
      SQLException failure =
          assertThrows(
              SQLException.class,
              () ->
                  new TransactionRetry(4, delay -> fail("禁止等待重试"))
                      .run(
                          db,
                          connection -> {
                            attempts.incrementAndGet();
                            throw error;
                          }));
      assertSame(error, failure);
      assertEquals(1, attempts.get());
    }
  }

  @Test
  void 等待被中断停止重试并恢复中断标志() throws Exception {
    var db = database();
    var attempts = new AtomicInteger();
    try {
      SQLException failure =
          assertThrows(
              SQLException.class,
              () ->
                  new TransactionRetry(
                          4,
                          delay -> {
                            throw new InterruptedException("停止请求");
                          })
                      .run(
                          db,
                          connection -> {
                            attempts.incrementAndGet();
                            throw deadlock();
                          }));
      assertEquals("57014", failure.getSQLState());
      assertEquals(1, attempts.get());
      assertTrue(Thread.currentThread().isInterrupted());
    } finally {
      Thread.interrupted();
    }
  }
}
