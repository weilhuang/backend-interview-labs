package labs;

import static org.junit.jupiter.api.Assertions.*;

import labs.support.RedisLab;
import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import redis.clients.jedis.Jedis;
import redis.clients.jedis.exceptions.JedisDataException;

@Tag("integration")
class StructuresIntegrationTest {
  @Test
  void structuresAndAtomicCounterHaveVisibleContracts() {
    try (RedisLab lab = new RedisLab().start();
        Jedis j = lab.connect()) {
      String p = lab.key("structures:");
      Structures.seed(j, p);
      assertEquals("u7", j.hget(p + "session", "user"));
      assertEquals(2, j.scard(p + "seen"));
      assertEquals("u8", j.zrevrange(p + "rank", 0, 0).getFirst());
      assertEquals(1, j.xlen(p + "events"));
      assertEquals(1, Structures.incrementWithTtl(j, p + "count", 30_000));
      long before = j.pttl(p + "count");
      assertTrue(before > 0 && before <= 30_000);
      assertEquals(2, Structures.incrementWithTtl(j, p + "count", 90_000));
      assertTrue(j.pttl(p + "count") <= before, "计数续增不能滑动延长固定窗口");
    }
  }

  @Test
  void invalidTtlMustNotIncrementBeforeAnExpiryError() {
    try (RedisLab lab = new RedisLab().start();
        Jedis j = lab.connect()) {
      String key = lab.key("ttl-overflow");
      assertThrows(
          IllegalArgumentException.class,
          () -> Structures.incrementWithTtl(j, key, Long.MAX_VALUE));
      assertFalse(j.exists(key));
      j.set(key, "not-an-integer");
      assertThrows(JedisDataException.class, () -> Structures.incrementWithTtl(j, key, 1000));
      assertEquals("not-an-integer", j.get(key));
    }
  }

  @Test
  void pipelineDoesNotRollbackAnEarlierOrLaterCommand() {
    try (RedisLab lab = new RedisLab().start();
        Jedis j = lab.connect()) {
      String k = lab.key("pipeline");
      j.set(k, "text");
      try (var pipeline = j.pipelined()) {
        var first = pipeline.set(k + ":first", "yes");
        var bad = pipeline.hset(k, "field", "value");
        var last = pipeline.set(k + ":last", "yes");
        pipeline.sync();
        assertEquals("OK", first.get());
        assertThrows(JedisDataException.class, bad::get);
        assertEquals("OK", last.get());
      }
      assertEquals("text", j.get(k));
      assertEquals("yes", j.get(k + ":last"));
    }
  }

  @Test
  void luaIsolationDoesNotMeanRollbackOnRuntimeErrors() {
    try (RedisLab lab = new RedisLab().start();
        Jedis j = lab.connect()) {
      String k = lab.key("lua:error");
      assertThrows(
          JedisDataException.class,
          () ->
              j.eval(
                  "redis.call('SET',KEYS[1],'kept'); return redis.call('HSET',KEYS[1],'x','y')",
                  java.util.List.of(k),
                  java.util.List.of()));
      assertEquals("kept", j.get(k), "脚本出错不回滚已经完成的写入");
    }
  }
}
