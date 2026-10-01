package labs.distributed.outbox;

import java.time.Duration;
import java.util.List;
import java.util.Optional;
import redis.clients.jedis.JedisPooled;

/** 版本下界键保留，值有TTL；元数据丢失后的保证降级在教材中明确列出。 */
public final class VersionedCache implements AutoCloseable {
  private final JedisPooled redis;
  private final long ttl;

  public VersionedCache(String host, int port, Duration ttl) {
    if (ttl.isNegative() || ttl.toMillis() < 1) throw new IllegalArgumentException("缓存TTL必须为正");
    this.redis = new JedisPooled(host, port);
    this.ttl = ttl.toMillis();
  }

  public boolean fill(Event snapshot) {
    // 练习区开始
    String script =
        "local f=tonumber(redis.call('GET',KEYS[1]) or '0'); local v=tonumber(ARGV[1]); if v<f then"
            + " return 0 end; redis.call('SET',KEYS[1],ARGV[1]);"
            + " redis.call('HSET',KEYS[2],'version',ARGV[1],'payload',ARGV[2]);"
            + " redis.call('PEXPIRE',KEYS[2],ARGV[3]); return 1";
    return ((Number)
                redis.eval(
                    script,
                    List.of("floor:" + snapshot.sku(), "cache:" + snapshot.sku()),
                    List.of(
                        Long.toString(snapshot.version()), snapshot.encode(), Long.toString(ttl))))
            .longValue()
        == 1;
    // 练习区结束
  }

  public void invalidate(Event event) {
    // 练习区开始
    String script =
        "local f=tonumber(redis.call('GET',KEYS[1]) or '0'); local v=tonumber(ARGV[1]); "
            + "if v>f then redis.call('SET',KEYS[1],ARGV[1]) end; "
            + "local c=tonumber(redis.call('HGET',KEYS[2],'version') or '0'); "
            + "if c<v then redis.call('DEL',KEYS[2]) end; return 1";
    redis.eval(
        script,
        List.of("floor:" + event.sku(), "cache:" + event.sku()),
        List.of(Long.toString(event.version())));
    // 练习区结束
  }

  public Optional<Event> get(String sku) {
    String value = redis.hget("cache:" + sku, "payload");
    return value == null ? Optional.empty() : Optional.of(Event.decode(value));
  }

  @Override
  public void close() {
    redis.close();
  }
}
