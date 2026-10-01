package labs.distributed;

import static org.junit.jupiter.api.Assertions.*;

import java.time.Duration;
import java.util.concurrent.*;
import labs.distributed.idempotency.IdempotencyStore;
import labs.distributed.idempotency.TransactionRetry;
import labs.distributed.support.*;
import org.junit.jupiter.api.Test;

class MySqlIdempotencyTest {
  @Test
  void 并发同键只扣一次且进程重建可查询未知结果() throws Exception {
    try (var mysql = Images.mysql()) {
      mysql.start();
      var db = Images.database(mysql);
      var store = new IdempotencyStore(db);
      store.initialize(10);
      var request = new IdempotencyStore.Request("same-key", "book", 3);
      var start = new CyclicBarrier(8);
      try (var pool = Executors.newFixedThreadPool(8)) {
        var claims =
            pool.invokeAll(
                java.util.stream.IntStream.range(0, 8)
                    .mapToObj(
                        i ->
                            (Callable<IdempotencyStore.Claim>)
                                () -> {
                                  start.await(5, TimeUnit.SECONDS);
                                  return store.acquire(request, Duration.ofSeconds(30));
                                })
                    .toList());
        var owners = new java.util.ArrayList<IdempotencyStore.Claim>();
        for (var result : claims)
          if (result.get().kind() == IdempotencyStore.Kind.OWNED) owners.add(result.get());
        assertEquals(1, owners.size());
        assertEquals(7, store.complete(request, owners.getFirst(), () -> {}));
      }
      // 重启真实MySQL进程并重建服务对象，验证已提交幂等结果的持久性。
      db = Images.restartAndAwait(mysql);
      var restarted = new IdempotencyStore(db);
      assertEquals(7, restarted.query(request.key()).orElseThrow());
      assertEquals(7, restarted.acquire(request, Duration.ofSeconds(10)).result());
      assertEquals(7, db.scalar("SELECT available FROM inventory"));
    }
  }

  @Test
  void 真实连接断开回滚本地更新并允许租约接管() throws Exception {
    try (var mysql = Images.mysql()) {
      mysql.start();
      var db = Images.database(mysql);
      var store = new IdempotencyStore(db);
      store.initialize(5);
      var request = new IdempotencyStore.Request("recover", "book", 2);
      var old = store.acquire(request, Duration.ofSeconds(30));
      // 真正关闭未提交连接，数据库应回滚，不只是抛Java异常。
      try (var connection = db.open()) {
        connection.setAutoCommit(false);
        Database.update(connection, "UPDATE inventory SET available=available-2 WHERE sku='book'");
      }
      assertEquals(5, db.scalar("SELECT available FROM inventory"));
      db.execute("UPDATE operations SET lease_until=0 WHERE op_key='recover'");
      var replacement = new IdempotencyStore(db).acquire(request, Duration.ofSeconds(30));
      assertThrows(IllegalStateException.class, () -> store.complete(request, old, () -> {}));
      assertEquals(3, store.complete(request, replacement, () -> {}));
      assertEquals(3, db.scalar("SELECT available FROM inventory"));
    }
  }

  @Test
  void 登记提交后退出领取流程仍可被新实例恢复() throws Exception {
    try (var mysql = Images.mysql()) {
      mysql.start();
      var db = Images.database(mysql);
      var store = new IdempotencyStore(db);
      store.initialize(10);
      var request = new IdempotencyStore.Request("registered-crash", "book", 2);
      assertThrows(
          IllegalStateException.class,
          () ->
              store.acquire(
                  request,
                  Duration.ofSeconds(10),
                  () -> {
                    throw new IllegalStateException("登记提交后退出领取流程");
                  }));
      assertEquals(10, db.scalar("SELECT available FROM inventory"));
      assertEquals(
          1,
          db.scalar(
              "SELECT COUNT(*) FROM operations WHERE generation=0 AND owner IS NULL AND"
                  + " lease_until=0"));
      var replacement = new IdempotencyStore(Images.database(mysql));
      assertThrows(
          IllegalArgumentException.class,
          () ->
              replacement.acquire(
                  new IdempotencyStore.Request(request.key(), "book", 3), Duration.ofSeconds(10)));
      var claim = replacement.acquire(request, Duration.ofSeconds(10));
      assertEquals(IdempotencyStore.Kind.OWNED, claim.kind());
      assertEquals(8, replacement.complete(request, claim, () -> {}));
      assertEquals(8, replacement.query(request.key()).orElseThrow());
    }
  }

  @Test
  void 真实死锁受害者重新执行完整事务且各行仅增加两次() throws Exception {
    try (var mysql = Images.mysql()) {
      mysql.start();
      var db = Images.database(mysql);
      db.execute("CREATE TABLE retry_stock(id INT PRIMARY KEY, applied INT NOT NULL)");
      db.execute("INSERT INTO retry_stock VALUES(1,0),(2,0)");
      var firstUpdates = new CyclicBarrier(2);
      var attempts = new java.util.concurrent.atomic.AtomicInteger();
      try (var pool = Executors.newFixedThreadPool(2)) {
        var results = new java.util.ArrayList<Future<Integer>>();
        for (int first : java.util.List.of(1, 2)) {
          results.add(
              pool.submit(
                  () -> {
                    var localAttempts = new java.util.concurrent.atomic.AtomicInteger();
                    return TransactionRetry.bounded()
                        .run(
                            db,
                            connection -> {
                              attempts.incrementAndGet();
                              Database.update(
                                  connection,
                                  "UPDATE retry_stock SET applied=applied+1 WHERE id=?",
                                  first);
                              if (localAttempts.getAndIncrement() == 0) {
                                try {
                                  firstUpdates.await(5, TimeUnit.SECONDS);
                                } catch (InterruptedException interrupted) {
                                  Thread.currentThread().interrupt();
                                  throw new java.sql.SQLException("死锁实验被中断", "57014", interrupted);
                                } catch (BrokenBarrierException | TimeoutException failure) {
                                  throw new java.sql.SQLException("未形成预定的双事务时序", failure);
                                }
                              }
                              Database.update(
                                  connection,
                                  "UPDATE retry_stock SET applied=applied+1 WHERE id=?",
                                  3 - first);
                              return 2;
                            });
                  }));
        }
        for (var result : results) assertEquals(2, result.get(20, TimeUnit.SECONDS));
      }
      assertEquals(3, attempts.get());
      assertEquals(2, db.scalar("SELECT applied FROM retry_stock WHERE id=1"));
      assertEquals(2, db.scalar("SELECT applied FROM retry_stock WHERE id=2"));
    }
  }
}
