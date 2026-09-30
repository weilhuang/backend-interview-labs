package labs.distributed;

import static org.junit.jupiter.api.Assertions.*;

import io.github.resilience4j.bulkhead.BulkheadFullException;
import io.github.resilience4j.circuitbreaker.CallNotPermittedException;
import io.github.resilience4j.circuitbreaker.CircuitBreaker;
import java.time.Duration;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicLong;
import org.junit.jupiter.api.Test;

class LabTest {
  @Test
  void 令牌耗尽及精确补充边界() {
    AtomicLong clock = new AtomicLong();
    var bucket = new Lab.TokenBucket(2, 2, clock::get);
    assertTrue(bucket.allow());
    assertTrue(bucket.allow());
    assertFalse(bucket.allow());
    clock.set(499_999_999);
    assertFalse(bucket.allow());
    clock.incrementAndGet();
    assertTrue(bucket.allow());
    assertFalse(bucket.allow());
    clock.addAndGet(10_000_000_000L);
    assertTrue(bucket.allow());
    assertTrue(bucket.allow());
    assertFalse(bucket.allow());
  }

  @Test
  void 滑动窗口左边界淘汰且不同于固定窗口() {
    AtomicLong clock = new AtomicLong(900_000_000);
    var window = new Lab.SlidingWindow(2, Duration.ofSeconds(1), clock::get);
    assertTrue(window.allow());
    assertTrue(window.allow());
    clock.set(1_000_000_000);
    assertFalse(window.allow());
    clock.set(1_899_999_999);
    assertFalse(window.allow());
    clock.incrementAndGet();
    assertTrue(window.allow());
  }

  @Test
  void 真实熔断器打开半开与恢复() throws Exception {
    var guard = new Lab.Guard(System::nanoTime);
    for (int i = 0; i < 4; i++)
      assertThrows(
          java.io.IOException.class,
          () ->
              guard.call(
                  () -> {
                    throw new java.io.IOException("注入失败");
                  }));
    assertEquals(CircuitBreaker.State.OPEN, guard.breaker.getState());
    assertThrows(CallNotPermittedException.class, () -> guard.call(() -> "不应执行"));
    guard.breaker.transitionToHalfOpenState();
    assertEquals("恢复", guard.call(() -> "恢复"));
    assertEquals(CircuitBreaker.State.HALF_OPEN, guard.breaker.getState());
    guard.call(() -> "第二次探测");
    assertEquals(CircuitBreaker.State.CLOSED, guard.breaker.getState());
  }

  @Test
  void 并发隔离饱和后立即拒绝且异常释放许可() throws Exception {
    var guard = new Lab.Guard(System::nanoTime);
    CountDownLatch entered = new CountDownLatch(2);
    CountDownLatch release = new CountDownLatch(1);
    try (var pool = Executors.newFixedThreadPool(2)) {
      Callable<String> call =
          () ->
              guard.call(
                  () -> {
                    entered.countDown();
                    if (!release.await(3, TimeUnit.SECONDS))
                      throw new IllegalStateException("测试屏障超时");
                    return "完成";
                  });
      Future<String> a = pool.submit(call);
      Future<String> b = pool.submit(call);
      try {
        assertTrue(entered.await(3, TimeUnit.SECONDS));
        assertThrows(BulkheadFullException.class, () -> guard.call(() -> "禁止排队"));
        assertEquals(0, guard.breaker.getMetrics().getNumberOfFailedCalls());
      } finally {
        release.countDown();
      }
      assertEquals("完成", a.get(3, TimeUnit.SECONDS));
      assertEquals("完成", b.get(3, TimeUnit.SECONDS));
    }
    assertEquals(2, guard.bulkhead.getMetrics().getAvailableConcurrentCalls());
  }

  @Test
  void 多线程共用同一个令牌桶不会超发() throws Exception {
    var bucket = new Lab.TokenBucket(7, 1, () -> 0);
    try (var pool = Executors.newFixedThreadPool(8)) {
      var results =
          pool.invokeAll(
              java.util.stream.IntStream.range(0, 80)
                  .mapToObj(i -> (Callable<Boolean>) bucket::allow)
                  .toList());
      int accepted = 0;
      for (var result : results) if (result.get()) accepted++;
      assertEquals(7, accepted);
    }
  }
}
