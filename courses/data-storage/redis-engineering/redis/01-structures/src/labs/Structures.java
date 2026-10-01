package labs;

import java.util.List;
import java.util.Map;
import redis.clients.jedis.Jedis;
import redis.clients.jedis.StreamEntryID;

/** 真实Redis结构与原子组合；键由调用方提供隔离命名空间。 */
public final class Structures {
  private Structures() {}

  public static long incrementWithTtl(Jedis redis, String key, long ttlMillis) {
    // 学员实现开始
    if (ttlMillis <= 0 || ttlMillis > 86_400_000)
      throw new IllegalArgumentException("计数窗口必须为1毫秒至24小时");
    return (Long)
        redis.eval(
            """
            local n = redis.call('INCR', KEYS[1])
            if n == 1 then redis.call('PEXPIRE', KEYS[1], ARGV[1]) end
            return n
            """,
            List.of(key),
            List.of(Long.toString(ttlMillis)));
    // 学员实现结束
  }

  public static void seed(Jedis redis, String prefix) {
    redis.hset(prefix + "session", Map.of("user", "u7", "role", "reader"));
    redis.pexpire(prefix + "session", 60_000);
    redis.sadd(prefix + "seen", "order-7", "order-7", "order-8");
    redis.zadd(prefix + "rank", 12, "u7");
    redis.zadd(prefix + "rank", 18, "u8");
    redis.xadd(
        prefix + "events", StreamEntryID.NEW_ENTRY, Map.of("order", "order-7", "state", "paid"));
  }
}
