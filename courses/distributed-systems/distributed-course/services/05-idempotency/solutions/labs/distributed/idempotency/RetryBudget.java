package labs.distributed.idempotency;

import java.time.Duration;
import java.util.function.LongSupplier;
import java.util.random.RandomGenerator;

public record RetryBudget(
    int maxAttempts, Duration total, Duration baseBackoff, Duration maxBackoff) {
  @FunctionalInterface
  public interface Attempt<T> {
    T call(Duration remaining) throws Exception;
  }

  @FunctionalInterface
  public interface Sleeper {
    void sleep(Duration duration) throws InterruptedException;
  }

  public static final class TransientFailure extends Exception {
    public TransientFailure(String message) {
      super(message);
    }
  }

  public RetryBudget {
    if (maxAttempts < 1
        || maxAttempts > 10
        || total.isNegative()
        || total.isZero()
        || baseBackoff.isNegative()
        || maxBackoff.compareTo(baseBackoff) < 0) {
      throw new IllegalArgumentException("重试配置非法");
    }
    total.toNanos();
    baseBackoff.toNanos();
    maxBackoff.toNanos();
  }

  public <T> T execute(
      boolean safeToRetry,
      Attempt<T> action,
      LongSupplier clock,
      Sleeper sleeper,
      RandomGenerator random)
      throws Exception {
    long start = clock.getAsLong();
    Exception last = null;
    // 练习区开始
    for (int attempt = 0; attempt < maxAttempts; attempt++) {
      long remaining = total.toNanos() - (clock.getAsLong() - start);
      if (remaining <= 0) break;
      try {
        return action.call(Duration.ofNanos(remaining));
      } catch (TransientFailure failure) {
        last = failure;
        if (!safeToRetry || attempt + 1 == maxAttempts) throw failure;
      }
      long base = baseBackoff.toNanos();
      long upper =
          base > (Long.MAX_VALUE >> attempt)
              ? maxBackoff.toNanos()
              : Math.min(maxBackoff.toNanos(), base << attempt);
      long delay = upper == 0 ? 0 : random.nextLong(upper);
      remaining = total.toNanos() - (clock.getAsLong() - start);
      if (remaining <= delay) break;
      sleeper.sleep(Duration.ofNanos(delay));
    }
    throw new TransientFailure("总预算耗尽，最后错误：" + (last == null ? "调用前已过期" : last.getMessage()));
    // 练习区结束
  }
}
