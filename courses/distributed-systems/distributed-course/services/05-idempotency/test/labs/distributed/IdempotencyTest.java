package labs.distributed;

import static org.junit.jupiter.api.Assertions.*;

import java.time.Duration;
import java.util.UUID;
import labs.distributed.idempotency.IdempotencyStore;
import labs.distributed.support.Database;
import org.junit.jupiter.api.Test;

/** H2仅作SQL合同快测，MySQL锁、断连与恢复只能由集成测试证明。 */
class IdempotencyTest {
  @Test
  void 领取处理中重入冲突及完成回放() throws Exception {
    var db =
        new Database(
            "jdbc:h2:mem:" + UUID.randomUUID() + ";MODE=MySQL;DB_CLOSE_DELAY=-1", "sa", "");
    var store = new IdempotencyStore(db);
    store.initialize(10);
    var request = new IdempotencyStore.Request("tenant:reserve:k1", "book", 2);
    var owner = store.acquire(request, Duration.ofSeconds(10));
    assertEquals(IdempotencyStore.Kind.OWNED, owner.kind());
    assertEquals(IdempotencyStore.Kind.BUSY, store.acquire(request, Duration.ofSeconds(10)).kind());
    assertThrows(
        IllegalArgumentException.class,
        () ->
            store.acquire(
                new IdempotencyStore.Request(request.key(), "book", 3), Duration.ofSeconds(10)));
    assertEquals(8, store.complete(request, owner, () -> {}));
    assertEquals(
        IdempotencyStore.Kind.REPLAY, store.acquire(request, Duration.ofSeconds(10)).kind());
    assertEquals(8, store.complete(request, owner, () -> {}));
    assertEquals(8, db.scalar("SELECT available FROM inventory WHERE sku='book'"));
  }

  @Test
  void 库存更新后故障回滚与旧租约代次被拒绝() throws Exception {
    var db =
        new Database(
            "jdbc:h2:mem:" + UUID.randomUUID() + ";MODE=MySQL;DB_CLOSE_DELAY=-1", "sa", "");
    var store = new IdempotencyStore(db);
    store.initialize(4);
    var request = new IdempotencyStore.Request("k1", "book", 3);
    var old = store.acquire(request, Duration.ofSeconds(10));
    assertThrows(
        IllegalStateException.class,
        () ->
            store.complete(
                request,
                old,
                () -> {
                  throw new IllegalStateException("提交前崩溃");
                }));
    assertEquals(4, db.scalar("SELECT available FROM inventory"));
    assertTrue(store.query("k1").isEmpty());
    db.execute("UPDATE operations SET lease_until=0 WHERE op_key='k1'");
    var current = store.acquire(request, Duration.ofSeconds(10));
    assertTrue(current.generation() > old.generation());
    assertThrows(IllegalStateException.class, () -> store.complete(request, old, () -> {}));
    assertEquals(1, store.complete(request, current, () -> {}));
  }
}
