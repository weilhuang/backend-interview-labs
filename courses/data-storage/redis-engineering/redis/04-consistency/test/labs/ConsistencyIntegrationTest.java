package labs;

import static org.junit.jupiter.api.Assertions.*;

import labs.support.*;
import org.junit.jupiter.api.*;

@Tag("integration")
class ConsistencyIntegrationTest {
  @Test
  void reproducibleStaleRefillAndDurableRecoveryAcrossPublisherRestart() throws Exception {
    try (var db = new MySqlLab().start();
        var lab = new RedisLab().start();
        var j = lab.connect()) {
      var store = new Consistency.Store(db::connect);
      store.initialize();
      String prefix = lab.key("aside:");
      var stale = store.read(1); // 读者A已经读到旧库值，尚未填缓存。
      var current = store.update(1, "新价格"); // 写库与outbox处于同一MySQL事务。
      j.del(Consistency.key(prefix, 1)); // 普通cache-aside删除后，A仍能回填旧值。
      assertTrue(Consistency.fill(j, prefix, 1, stale, 30_000));
      assertEquals(stale, Consistency.read(store, j, prefix, 1));
      assertEquals(1, store.pending());
      // Redis送达、DB确认之前故障：已失效但outbox仍待发，重启发布器可重复投递。
      assertThrows(
          IllegalStateException.class,
          () ->
              store.recover(
                  j,
                  prefix,
                  10,
                  () -> {
                    throw new IllegalStateException("模拟发送后确认前进程退出");
                  }));
      assertEquals(1, store.pending());
      assertNull(j.get(Consistency.key(prefix, 1)));
      var restarted = new Consistency.Store(db::connect);
      assertEquals(1, restarted.recover(j, prefix, 10, () -> {}));
      assertEquals(0, restarted.pending());
      assertFalse(Consistency.fill(j, prefix, 1, stale, 30_000), "持久水位拒绝延迟旧回填");
      assertEquals(current, Consistency.read(restarted, j, prefix, 1));
      Consistency.invalidate(j, prefix, 1, 1);
      assertEquals(current, Consistency.read(restarted, j, prefix, 1));
      assertEquals(-1, j.pttl(Consistency.watermark(prefix, 1)), "水位不跟随数据TTL过期");
    }
  }

  @Test
  void redisDeliveryFailureLeavesTransactionEventRecoverable() throws Exception {
    try (var db = new MySqlLab().start();
        var lab = new RedisLab().start();
        var j = lab.connect()) {
      var store = new Consistency.Store(db::connect);
      store.initialize();
      String prefix = lab.key("failure:");
      store.update(1, "已提交");
      lab.crash();
      assertThrows(RuntimeException.class, () -> store.recover(j, prefix, 1, () -> {}));
      assertEquals(1, store.pending());
      lab.restart();
      try (var recovered = lab.connect()) {
        assertEquals(1, store.recover(recovered, prefix, 1, () -> {}));
        assertEquals("已提交", Consistency.read(store, recovered, prefix, 1).value());
      }
    }
  }

  @Test
  void lostWatermarkRequiresReadinessGateAndDatabaseRebuild() throws Exception {
    try (var db = new MySqlLab().start();
        var lab = new RedisLab("--save", "", "--appendonly", "no").start()) {
      var store = new Consistency.Store(db::connect);
      store.initialize();
      String prefix = lab.key("lost-floor:");
      var stale = store.read(1);
      var fresh = store.update(1, "新事实");
      try (var j = lab.connect()) {
        store.recover(j, prefix, 10, () -> {});
      }
      assertEquals(0, store.pending());
      lab.crash();
      lab.restart();
      try (var j = lab.connect()) {
        assertTrue(Consistency.fill(j, prefix, 1, stale, 30_000), "反例：Redis丢失水位后不能宣称版本保护仍有效");
        store.rebuildWatermark(j, prefix, 1); // 此前保持应用readiness关闭，拒绝外部读取。
        assertFalse(Consistency.fill(j, prefix, 1, stale, 30_000));
        assertEquals(fresh, Consistency.read(store, j, prefix, 1));
      }
    }
  }

  @Test
  void validationFailureRollsBackBothProductAndOutbox() throws Exception {
    try (var db = new MySqlLab().start()) {
      var store = new Consistency.Store(db::connect);
      store.initialize();
      assertThrows(IllegalArgumentException.class, () -> store.update(1, null));
      assertThrows(
          IllegalStateException.class,
          () ->
              store.update(
                  1,
                  "中途写入",
                  () -> {
                    throw new IllegalStateException("商品已写、事件未写时故障");
                  }));
      assertEquals(1, store.read(1).version());
      assertEquals(0, store.pending());
    }
  }
}
