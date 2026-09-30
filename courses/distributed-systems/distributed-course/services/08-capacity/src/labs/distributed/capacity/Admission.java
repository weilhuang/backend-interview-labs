package labs.distributed.capacity;

import java.util.concurrent.Callable;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.Semaphore;
import java.util.concurrent.atomic.AtomicInteger;

/** 无等待队列的并发准入，不用虚拟线程数量代替数据库容量限制。 */
public final class Admission {
  private final Semaphore permits;
  private final AtomicInteger active = new AtomicInteger();
  private final AtomicInteger peak = new AtomicInteger();

  public Admission(int maximum) {
    if (maximum < 1) throw new IllegalArgumentException("并发额度必须为正");
    permits = new Semaphore(maximum);
  }

  public <T> T execute(Callable<T> work) throws Exception {
    // 练习区开始
    if (!permits.tryAcquire()) throw new RejectedExecutionException("容量已满，请按预算退避");
    int current = active.incrementAndGet();
    peak.accumulateAndGet(current, Math::max);
    try {
      return work.call();
    } finally {
      active.decrementAndGet();
      permits.release();
    }
    // 练习区结束
  }

  public int active() {
    return active.get();
  }

  public int peak() {
    return peak.get();
  }

  public static int requiredConcurrency(
      double requestsPerSecond, double latencySeconds, double headroom) {
    // 练习区开始
    double demand = requestsPerSecond * latencySeconds * headroom;
    if (!Double.isFinite(demand)
        || requestsPerSecond <= 0
        || latencySeconds <= 0
        || headroom < 1
        || demand > Integer.MAX_VALUE) throw new IllegalArgumentException("容量参数非法或溢出");
    return Math.max(1, (int) Math.ceil(demand));
    // 练习区结束
  }
}
