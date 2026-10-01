package labs;

import java.time.Duration;
import java.util.Optional;
import java.util.concurrent.*;
import java.util.concurrent.atomic.LongAdder;
import org.apache.commons.pool2.impl.GenericObjectPoolConfig;
import redis.clients.jedis.*;
import redis.clients.jedis.params.SetParams;

/** 有界连接、有界回源和可观测降级；不启动无限重试或无界后台刷新。 */
public final class Resilience implements AutoCloseable {
  public enum Source {
    CACHE,
    DATABASE,
    MISSING,
    UNAVAILABLE
  }

  public record Result(Optional<String> value, Source source) {}

  public record Metrics(
      long hits, long originCalls, long cacheErrors, long rejected, long timedOut) {}

  public interface Cache {
    String get(String key);

    void put(String key, String value);
  }

  @FunctionalInterface
  public interface Origin {
    Optional<String> read(String key) throws Exception;
  }

  public static final class RedisCache implements Cache, AutoCloseable {
    private final JedisPool pool;

    public RedisCache(String host, int port) {
      GenericObjectPoolConfig<Jedis> config = new GenericObjectPoolConfig<>();
      config.setMaxTotal(2);
      config.setMaxIdle(2);
      config.setMinIdle(0);
      config.setBlockWhenExhausted(true);
      config.setMaxWait(Duration.ofMillis(50));
      pool = new JedisPool(config, host, port, 150, 150, null, 0, null);
    }

    public String get(String key) {
      try (Jedis j = pool.getResource()) {
        return j.get(key);
      }
    }

    public void put(String key, String value) {
      try (Jedis j = pool.getResource()) {
        j.set(key, value, SetParams.setParams().px(30_000));
      }
    }

    public int activeConnections() {
      return pool.getNumActive();
    }

    @Override
    public void close() {
      pool.close();
    }
  }

  private final Cache cache;
  private final Origin origin;
  private final ThreadPoolExecutor workers;
  private final long originBudgetMillis;
  private final LongAdder hits = new LongAdder(),
      calls = new LongAdder(),
      errors = new LongAdder(),
      rejected = new LongAdder(),
      timeouts = new LongAdder();

  public Resilience(Cache cache, Origin origin, int concurrentOrigin, Duration originBudget) {
    if (concurrentOrigin < 1 || originBudget.toMillis() < 1)
      throw new IllegalArgumentException("回源并发和预算必须为正");
    this.cache = cache;
    this.origin = origin;
    this.originBudgetMillis = originBudget.toMillis();
    workers =
        new ThreadPoolExecutor(
            concurrentOrigin,
            concurrentOrigin,
            0,
            TimeUnit.MILLISECONDS,
            new SynchronousQueue<>(),
            new ThreadPoolExecutor.AbortPolicy());
  }

  public Result read(String key) {
    // 学员实现开始
    try {
      String hit = cache.get(key);
      if (hit != null) {
        hits.increment();
        return new Result(Optional.of(hit), Source.CACHE);
      }
    } catch (RuntimeException e) {
      errors.increment();
    }
    Future<Optional<String>> future;
    try {
      future =
          workers.submit(
              () -> {
                calls.increment();
                return origin.read(key);
              });
    } catch (RejectedExecutionException e) {
      rejected.increment();
      return unavailable();
    }
    try {
      Optional<String> value = future.get(originBudgetMillis, TimeUnit.MILLISECONDS);
      if (value.isEmpty()) return new Result(value, Source.MISSING);
      try {
        cache.put(key, value.orElseThrow());
      } catch (RuntimeException e) {
        errors.increment();
      }
      return new Result(value, Source.DATABASE);
    } catch (TimeoutException e) {
      timeouts.increment();
      future.cancel(true);
      return unavailable();
    } catch (InterruptedException e) {
      future.cancel(true);
      Thread.currentThread().interrupt();
      return unavailable();
    } catch (ExecutionException e) {
      return unavailable();
    }
    // 学员实现结束
  }

  private static Result unavailable() {
    return new Result(Optional.empty(), Source.UNAVAILABLE);
  }

  public Metrics metrics() {
    return new Metrics(hits.sum(), calls.sum(), errors.sum(), rejected.sum(), timeouts.sum());
  }

  public int activeOriginTasks() {
    return workers.getActiveCount();
  }

  @Override
  public void close() {
    workers.shutdownNow();
    try {
      if (!workers.awaitTermination(3, TimeUnit.SECONDS))
        throw new IllegalStateException("回源任务未响应取消；必须修复底层超时与资源关闭");
    } catch (InterruptedException e) {
      Thread.currentThread().interrupt();
    }
  }
}
