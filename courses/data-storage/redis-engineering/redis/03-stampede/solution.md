# C07-03 公开标准解

完整参考实现如下，与src/labs/Stampede.java自动同步。逐步讲解、复杂度、边界和替代方案在题面。学习者可随时查看；独立回测建议换数据/故障点后重写。

```java
package labs;

import java.time.Duration;
import java.util.HashMap;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;
import java.util.concurrent.*;
import java.util.random.RandomGenerator;
import redis.clients.jedis.Jedis;
import redis.clients.jedis.params.SetParams;

/** 单进程单飞；跨进程互斥和分布式故障不是此模型的保证。 */
public final class Stampede {
  private final Map<String, CompletableFuture<Optional<String>>> flights = new HashMap<>();
  private final java.util.concurrent.atomic.AtomicInteger waiting =
      new java.util.concurrent.atomic.AtomicInteger();
  private final int maximum;
  private final long waitMillis;

  public Stampede(int maximum, Duration wait) {
    if (maximum < 1 || wait.isNegative() || wait.isZero() || wait.toMillis() == 0)
      throw new IllegalArgumentException("容量和等待预算必须为正");
    this.maximum = maximum;
    this.waitMillis = wait.toMillis();
  }

  public Optional<String> load(String key, Callable<Optional<String>> loader) throws Exception {
    // 学员实现开始
    CompletableFuture<Optional<String>> future;
    boolean owner;
    synchronized (flights) {
      future = flights.get(key);
      owner = future == null;
      if (owner) {
        if (flights.size() >= maximum) throw new RejectedExecutionException("不同键回源容量已满");
        future = new CompletableFuture<>();
        flights.put(key, future);
      }
    }
    if (!owner) {
      waiting.incrementAndGet();
      try {
        return future.get(waitMillis, TimeUnit.MILLISECONDS);
      } catch (ExecutionException e) {
        throw new IllegalStateException("同键回源失败", e.getCause());
      } finally {
        waiting.decrementAndGet();
      }
    }
    try {
      Optional<String> value = Objects.requireNonNull(loader.call());
      future.complete(value);
      return value;
    } catch (Exception | Error e) {
      future.completeExceptionally(e);
      throw e;
    } finally {
      synchronized (flights) {
        flights.remove(key, future);
      }
    }
    // 学员实现结束
  }

  public int waiting() {
    return waiting.get();
  }

  public int inFlight() {
    synchronized (flights) {
      return flights.size();
    }
  }

  public static long jitter(long baseMillis, int percent, RandomGenerator random) {
    if (baseMillis <= 0 || percent < 0 || percent > 50 || baseMillis > Long.MAX_VALUE / 2)
      throw new IllegalArgumentException("抖动参数越界");
    long spread = baseMillis / 100 * percent;
    return baseMillis + (spread == 0 ? 0 : random.nextLong(-spread, spread + 1));
  }

  /** 每次Supplier调用必须返回由本方法独占且负责关闭的连接，禁止共享单个Jedis。 */
  public Optional<String> cached(
      java.util.function.Supplier<Jedis> connections,
      String key,
      Callable<Optional<String>> origin,
      long positiveTtl,
      long negativeTtl)
      throws Exception {
    if (negativeTtl <= 0 || positiveTtl < negativeTtl)
      throw new IllegalArgumentException("负缓存TTL必须为正且不大于正缓存");
    try (Jedis redis = connections.get()) {
      String value = redis.get(key);
      if (value != null) return decode(value);
    }
    return load(
        key,
        () -> {
          try (Jedis redis = connections.get()) {
            String again = redis.get(key);
            if (again != null) return decode(again);
          }
          Optional<String> loaded = origin.call();
          try (Jedis redis = connections.get()) {
            redis.set(
                key,
                loaded.map(v -> "v:" + v).orElse("n:"),
                SetParams.setParams().px(loaded.isPresent() ? positiveTtl : negativeTtl));
          }
          return loaded;
        });
  }

  private static Optional<String> decode(String text) {
    if (text.equals("n:")) return Optional.empty();
    if (!text.startsWith("v:")) throw new IllegalStateException("未知缓存编码");
    return Optional.of(text.substring(2));
  }
}
```
