package labs;

import static org.junit.jupiter.api.Assertions.*;

import java.time.Duration;
import java.util.Optional;
import java.util.concurrent.*;
import org.junit.jupiter.api.Test;

class ResilienceTest {
  private static final Resilience.Cache MISS =
      new Resilience.Cache() {
        public String get(String k) {
          return null;
        }

        public void put(String k, String v) {}
      };

  @Test
  void hitDoesNotTouchOriginAndFailureDegrades() {
    var hit =
        new Resilience.Cache() {
          public String get(String k) {
            return "cached";
          }

          public void put(String k, String v) {
            fail("命中不回填");
          }
        };
    try (var service =
        new Resilience(
            hit,
            k -> {
              fail("命中不回源");
              return Optional.empty();
            },
            1,
            Duration.ofSeconds(1))) {
      assertEquals(Resilience.Source.CACHE, service.read("x").source());
      assertEquals(1, service.metrics().hits());
      assertEquals(0, service.metrics().originCalls());
    }
    var broken =
        new Resilience.Cache() {
          public String get(String k) {
            throw new IllegalStateException("Redis不可用");
          }

          public void put(String k, String v) {
            throw new IllegalStateException("Redis不可用");
          }
        };
    try (var service = new Resilience(broken, k -> Optional.of("db"), 1, Duration.ofSeconds(1))) {
      assertEquals(Resilience.Source.DATABASE, service.read("x").source());
      assertEquals(2, service.metrics().cacheErrors());
    }
  }

  @Test
  void saturationRejectsAndTimeoutDoesNotPretendUnderlyingWorkStopped() throws Exception {
    CountDownLatch entered = new CountDownLatch(1), release = new CountDownLatch(1);
    try (var service =
            new Resilience(
                MISS,
                k -> {
                  entered.countDown();
                  while (release.getCount() > 0) {
                    try {
                      release.await();
                    } catch (InterruptedException ignored) {
                      /* 教学故障：模拟不响应中断的阻塞驱动。 */
                    }
                  }
                  return Optional.of("late");
                },
                1,
                Duration.ofMillis(40));
        var caller = Executors.newSingleThreadExecutor()) {
      try {
        var first = caller.submit(() -> service.read("first"));
        assertTrue(entered.await(2, TimeUnit.SECONDS));
        assertEquals(Resilience.Source.UNAVAILABLE, service.read("second").source());
        assertEquals(Resilience.Source.UNAVAILABLE, first.get(2, TimeUnit.SECONDS).source());
        assertEquals(1, service.activeOriginTasks(), "取消Future不等于底层阻塞已停止");
        assertEquals(1, service.metrics().rejected());
        assertEquals(1, service.metrics().timedOut());
      } finally {
        release.countDown();
      }
    }
  }

  @Test
  void missingAndOriginErrorAreNotFabricatedSuccess() {
    try (var service = new Resilience(MISS, k -> Optional.empty(), 1, Duration.ofSeconds(1))) {
      assertEquals(Resilience.Source.MISSING, service.read("missing").source());
    }
    try (var service =
        new Resilience(
            MISS,
            k -> {
              throw new Exception("数据库错误");
            },
            1,
            Duration.ofSeconds(1))) {
      assertEquals(Resilience.Source.UNAVAILABLE, service.read("bad").source());
    }
  }
}
