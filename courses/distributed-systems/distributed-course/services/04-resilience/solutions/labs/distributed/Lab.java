package labs.distributed;

import io.github.resilience4j.bulkhead.Bulkhead;
import io.github.resilience4j.bulkhead.BulkheadConfig;
import io.github.resilience4j.circuitbreaker.CircuitBreaker;
import io.github.resilience4j.circuitbreaker.CircuitBreakerConfig;
import java.time.Duration;
import java.util.ArrayDeque;
import java.util.concurrent.Callable;
import java.util.function.LongSupplier;

public final class Lab {
  /** 教学令牌桶：单进程、同步临界区、单调纳秒时钟，不是全局限流。 */
  public static final class TokenBucket {
    private final double capacity;
    private final double perNano;
    private final LongSupplier clock;
    private double tokens;
    private long last;

    public TokenBucket(int capacity, double perSecond, LongSupplier clock) {
      if (capacity <= 0 || !Double.isFinite(perSecond) || perSecond <= 0) {
        throw new IllegalArgumentException("容量与补充速率必须大于零");
      }
      this.capacity = capacity;
      this.perNano = perSecond / 1_000_000_000.0;
      this.clock = clock;
      this.tokens = capacity;
      this.last = clock.getAsLong();
    }

    public synchronized boolean allow() {
      // 练习区开始
      long now = clock.getAsLong();
      long elapsed = now - last;
      if (elapsed < 0) {
        throw new IllegalStateException("单调时钟发生倒退，检查测试时钟或运行跨度");
      }
      tokens = Math.min(capacity, tokens + elapsed * perNano);
      last = now;
      if (tokens < 1.0) {
        return false;
      }
      tokens -= 1.0;
      return true;
      // 练习区结束
    }
  }

  /** 精确滑动日志：空间上限为额度，窗口为(now-window, now]。 */
  public static final class SlidingWindow {
    private final int limit;
    private final long window;
    private final LongSupplier clock;
    private final ArrayDeque<Long> accepted = new ArrayDeque<>();
    private long last = Long.MIN_VALUE;

    public SlidingWindow(int limit, Duration window, LongSupplier clock) {
      if (limit < 1 || window.isNegative() || window.isZero()) {
        throw new IllegalArgumentException("额度和窗口必须为正");
      }
      this.limit = limit;
      this.window = window.toNanos();
      this.clock = clock;
    }

    public synchronized boolean allow() {
      // 练习区开始
      long now = clock.getAsLong();
      if (now < last) throw new IllegalStateException("时钟倒退");
      last = now;
      while (!accepted.isEmpty() && now - accepted.peekFirst() >= window) {
        accepted.removeFirst();
      }
      if (accepted.size() == limit) return false;
      accepted.addLast(now);
      return true;
      // 练习区结束
    }
  }

  /** 真实库组合；限流拒绝与隔离拒绝不记作下游故障。 */
  public static final class Guard {
    public final CircuitBreaker breaker;
    public final Bulkhead bulkhead;
    public final TokenBucket rate;

    public Guard(LongSupplier clock) {
      rate = new TokenBucket(20, 20, clock);
      breaker =
          CircuitBreaker.of(
              "库存服务",
              CircuitBreakerConfig.custom()
                  .slidingWindowSize(4)
                  .minimumNumberOfCalls(4)
                  .failureRateThreshold(50)
                  .waitDurationInOpenState(Duration.ofSeconds(10))
                  .permittedNumberOfCallsInHalfOpenState(2)
                  .automaticTransitionFromOpenToHalfOpenEnabled(false)
                  .build());
      bulkhead =
          Bulkhead.of(
              "库存并发隔离",
              BulkheadConfig.custom().maxConcurrentCalls(2).maxWaitDuration(Duration.ZERO).build());
    }

    public <T> T call(Callable<T> downstream) throws Exception {
      // 练习区开始
      if (!rate.allow()) throw new IllegalStateException("入口限流拒绝");
      return Bulkhead.decorateCallable(
              bulkhead, CircuitBreaker.decorateCallable(breaker, downstream))
          .call();
      // 练习区结束
    }
  }
}
