package labs;

import static org.junit.jupiter.api.Assertions.*;

import java.time.Duration;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.Test;

class StampedeTest {
  @Test
  void oneOwnerWithBoundedJoinersAndCapacityProtection() throws Exception {
    Stampede s = new Stampede(1, Duration.ofSeconds(2));
    CountDownLatch entered = new CountDownLatch(1), release = new CountDownLatch(1);
    AtomicInteger calls = new AtomicInteger();
    try (var pool = Executors.newFixedThreadPool(2)) {
      var owner =
          pool.submit(
              () ->
                  s.load(
                      "k",
                      () -> {
                        calls.incrementAndGet();
                        entered.countDown();
                        assertTrue(release.await(2, TimeUnit.SECONDS));
                        return Optional.of("value");
                      }));
      assertTrue(entered.await(2, TimeUnit.SECONDS));
      assertThrows(RejectedExecutionException.class, () -> s.load("other", Optional::empty));
      var follower =
          pool.submit(
              () ->
                  s.load(
                      "k",
                      () -> {
                        calls.incrementAndGet();
                        return Optional.of("value");
                      }));
      // 等到单飞公开观测状态确认跟随者已经加入，再释放所有者。
      long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(2);
      while (s.waiting() != 1 && System.nanoTime() < deadline) Thread.onSpinWait();
      assertEquals(1, s.waiting());
      release.countDown();
      assertEquals(Optional.of("value"), owner.get(2, TimeUnit.SECONDS));
      assertEquals(Optional.of("value"), follower.get(2, TimeUnit.SECONDS));
      assertEquals(1, calls.get(), "重叠的同键请求只允许一个实际回源");
      assertEquals(0, s.inFlight());
    } finally {
      release.countDown();
    }
  }

  @Test
  void failureReleasesCapacityAndNegativeResultIsAValue() throws Exception {
    Stampede s = new Stampede(1, Duration.ofSeconds(1));
    assertThrows(
        Exception.class,
        () ->
            s.load(
                "x",
                () -> {
                  throw new Exception("数据库失败");
                }));
    assertEquals(0, s.inFlight());
    assertEquals(Optional.empty(), s.load("x", Optional::empty));
  }

  @Test
  void jitterRemainsWithinDeclaredRangeWithFixedSeed() {
    Random random = new Random(7);
    Set<Long> observed = new HashSet<>();
    for (int i = 0; i < 1000; i++) {
      long value = Stampede.jitter(10_000, 20, random);
      assertTrue(value >= 8000 && value <= 12000);
      observed.add(value);
    }
    assertTrue(observed.size() > 1);
    assertEquals(100, Stampede.jitter(100, 0, random));
  }

  @Test
  void waitingFollowerCanTimeOutWithoutCancellingOwner() throws Exception {
    Stampede s = new Stampede(1, Duration.ofMillis(30));
    CountDownLatch entered = new CountDownLatch(1), release = new CountDownLatch(1);
    try (var pool = Executors.newSingleThreadExecutor()) {
      try {
        var owner =
            pool.submit(
                () ->
                    s.load(
                        "x",
                        () -> {
                          entered.countDown();
                          release.await();
                          return Optional.of("ok");
                        }));
        assertTrue(entered.await(2, TimeUnit.SECONDS));
        assertThrows(TimeoutException.class, () -> s.load("x", Optional::empty));
        assertEquals(1, s.inFlight());
        release.countDown();
        assertEquals(Optional.of("ok"), owner.get(2, TimeUnit.SECONDS));
      } finally {
        release.countDown();
      }
    } finally {
      release.countDown();
    }
  }
}
