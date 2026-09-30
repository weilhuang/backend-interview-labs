package labs.distributed;

import static org.junit.jupiter.api.Assertions.*;

import java.time.Duration;
import java.util.concurrent.*;
import labs.distributed.idempotency.IdempotencyStore;
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
      try (var pool = Executors.newFixedThreadPool(8)) {
        var claims =
            pool.invokeAll(
                java.util.stream.IntStream.range(0, 8)
                    .mapToObj(
                        i ->
                            (Callable<IdempotencyStore.Claim>)
                                () -> store.acquire(request, Duration.ofSeconds(30)))
                    .toList());
        var owners = new java.util.ArrayList<IdempotencyStore.Claim>();
        for (var result : claims)
          if (result.get().kind() == IdempotencyStore.Kind.OWNED) owners.add(result.get());
        assertEquals(1, owners.size());
        assertEquals(7, store.complete(request, owners.getFirst(), () -> {}));
      }
      // 重启真实MySQL进程并重建服务对象，验证已提交幂等结果的持久性。
      Images.restartAndAwait(mysql);
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
}
