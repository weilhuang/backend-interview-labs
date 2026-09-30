package labs;

import static org.junit.jupiter.api.Assertions.*;

import java.time.Duration;
import java.util.Optional;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicInteger;
import labs.support.RedisLab;
import org.junit.jupiter.api.*;

@Tag("integration")
class StampedeIntegrationTest {
  @Test
  void concurrentRealRedisReadsUseIndependentConnectionsAndOneOrigin() throws Exception {
    try (var lab = new RedisLab().start();
        var executor = Executors.newFixedThreadPool(4)) {
      Stampede s = new Stampede(2, Duration.ofSeconds(4));
      String key = lab.key("hot");
      AtomicInteger calls = new AtomicInteger();
      CountDownLatch entered = new CountDownLatch(1), release = new CountDownLatch(1);
      try {
        var owner =
            executor.submit(
                () ->
                    s.cached(
                        lab::connect,
                        key,
                        () -> {
                          calls.incrementAndGet();
                          entered.countDown();
                          assertTrue(release.await(4, TimeUnit.SECONDS));
                          return Optional.of("hot-value");
                        },
                        30_000,
                        2_000));
        assertTrue(entered.await(3, TimeUnit.SECONDS));
        var followers = new java.util.ArrayList<Future<Optional<String>>>();
        for (int i = 0; i < 3; i++)
          followers.add(
              executor.submit(
                  () ->
                      s.cached(
                          lab::connect,
                          key,
                          () -> {
                            calls.incrementAndGet();
                            return Optional.of("hot-value");
                          },
                          30_000,
                          2_000)));
        long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(3);
        while (s.waiting() != 3 && System.nanoTime() < deadline) Thread.onSpinWait();
        assertEquals(3, s.waiting());
        release.countDown();
        assertEquals(Optional.of("hot-value"), owner.get(3, TimeUnit.SECONDS));
        for (var follower : followers)
          assertEquals(Optional.of("hot-value"), follower.get(3, TimeUnit.SECONDS));
        assertEquals(1, calls.get());
        assertEquals(0, s.inFlight());
      } finally {
        release.countDown();
      }
    }
  }

  @Test
  void negativeCachingBoundsMissesAndCanBeInvalidated() throws Exception {
    try (var lab = new RedisLab().start();
        var j = lab.connect()) {
      Stampede s = new Stampede(2, Duration.ofSeconds(1));
      AtomicInteger loads = new AtomicInteger();
      String k = lab.key("missing");
      for (int i = 0; i < 8; i++)
        assertTrue(
            s.cached(
                    lab::connect,
                    k,
                    () -> {
                      loads.incrementAndGet();
                      return Optional.empty();
                    },
                    30_000,
                    2_000)
                .isEmpty());
      assertEquals(1, loads.get());
      assertTrue(j.pttl(k) > 0 && j.pttl(k) <= 2000);
      j.del(k);
      assertEquals(
          Optional.of("n:"), s.cached(lab::connect, k, () -> Optional.of("n:"), 30_000, 2_000));
      assertEquals(
          Optional.of("n:"),
          s.cached(
              lab::connect,
              k,
              () -> {
                fail("不得回源");
                return Optional.empty();
              },
              30_000,
              2_000));
    }
  }
}
