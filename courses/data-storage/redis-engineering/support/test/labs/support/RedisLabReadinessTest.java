package labs.support;

import static org.junit.jupiter.api.Assertions.*;

import java.time.Duration;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.Supplier;
import org.junit.jupiter.api.Test;
import redis.clients.jedis.Jedis;
import redis.clients.jedis.exceptions.JedisConnectionException;

/** 纯Java夹具契约；FakeJedis默认构造不连接网络，ping/close均在本类替代。 */
class RedisLabReadinessTest {
  private static final String PHASE = "primary.crash后、promote前";

  private static final class Clock {
    long nanos;
    void sleep(long delay) { nanos += delay; }
  }

  private static final class FakeJedis extends Jedis {
    Supplier<String> reply = () -> "PONG";
    RuntimeException closeFailure;
    int closes;

    @Override public String ping() { return reply.get(); }
    @Override public void close() {
      closes++;
      if (closeFailure != null) throw closeFailure;
    }
  }

  private Jedis ready(Supplier<Jedis> connections, Clock clock) {
    return RedisLab.connectReady(
        PHASE, connections, Duration.ofMillis(250), () -> clock.nanos, clock::sleep);
  }

  @Test
  void returnsTheSameReadyConnectionAndLeavesOwnershipWithCaller() {
    var connection = new FakeJedis();
    var calls = new AtomicInteger();
    try (var result = ready(() -> { calls.incrementAndGet(); return connection; }, new Clock())) {
      assertSame(connection, result);
      assertEquals(1, calls.get());
      assertEquals(0, connection.closes);
    }
    assertEquals(1, connection.closes);
  }

  @Test
  void constructorHandshakeFailureCanRecoverBeforeBusinessRuns() {
    var connection = new FakeJedis();
    var calls = new AtomicInteger();
    try (var result = ready(() -> {
      if (calls.incrementAndGet() == 1) throw new JedisConnectionException("handshake timeout");
      return connection;
    }, new Clock())) {
      assertSame(connection, result);
      assertEquals(2, calls.get());
    }
  }

  @Test
  void failedPingConnectionIsClosedBeforeAnotherIsOpened() {
    var failed = new FakeJedis();
    failed.reply = () -> { throw new JedisConnectionException("PING timeout"); };
    var healthy = new FakeJedis();
    var calls = new AtomicInteger();
    try (var result = ready(() -> {
      if (calls.incrementAndGet() == 1) return failed;
      assertEquals(1, failed.closes);
      return healthy;
    }, new Clock())) {
      assertSame(healthy, result);
      assertEquals(2, calls.get());
    }
  }

  @Test
  void sustainedHandshakeFailureStopsAtBudgetAndKeepsPhaseAndCause() {
    var clock = new Clock();
    var calls = new AtomicInteger();
    var timeout = new JedisConnectionException("last handshake timeout");
    var failure = assertThrows(RedisLab.FixtureReadinessException.class,
        () -> ready(() -> { calls.incrementAndGet(); throw timeout; }, clock));
    assertEquals(3, calls.get()); // t=0,100,200ms; no fourth attempt at the 250ms deadline.
    assertEquals(Duration.ofMillis(250).toNanos(), clock.nanos);
    assertSame(timeout, failure.getCause());
    assertTrue(failure.getMessage().contains(PHASE));
    assertTrue(failure.getMessage().contains("尝试次数=3"));
  }

  @Test
  void lateSuccessfulPingIsClosedRatherThanReturnedAfterBudget() {
    var clock = new Clock();
    var connection = new FakeJedis();
    connection.reply = () -> { clock.nanos = Duration.ofMillis(251).toNanos(); return "PONG"; };
    var calls = new AtomicInteger();
    assertThrows(RedisLab.FixtureReadinessException.class,
        () -> ready(() -> { calls.incrementAndGet(); return connection; }, clock));
    assertEquals(1, calls.get());
    assertEquals(1, connection.closes);
  }

  @Test
  void nonPongReplyFailsImmediatelyAndClosesConnection() {
    var connection = new FakeJedis();
    connection.reply = () -> "WRONG";
    var calls = new AtomicInteger();
    assertThrows(RedisLab.FixtureReadinessException.class,
        () -> ready(() -> { calls.incrementAndGet(); return connection; }, new Clock()));
    assertEquals(1, calls.get());
    assertEquals(1, connection.closes);
  }

  @Test
  void unrelatedRuntimeErrorIsNeverRetried() {
    var connection = new FakeJedis();
    var wrong = new IllegalArgumentException("configuration error");
    connection.reply = () -> { throw wrong; };
    var calls = new AtomicInteger();
    assertSame(wrong, assertThrows(IllegalArgumentException.class,
        () -> ready(() -> { calls.incrementAndGet(); return connection; }, new Clock())));
    assertEquals(1, calls.get());
    assertEquals(1, connection.closes);
  }

  @Test
  void callerBusinessFailureIsNotRetriedEvenWhenItIsAConnectionException() {
    var calls = new AtomicInteger();
    var businessCalls = new AtomicInteger();
    var businessFailure = new JedisConnectionException("failure inside promote");
    assertSame(businessFailure, assertThrows(JedisConnectionException.class, () -> {
      try (var connection = ready(() -> { calls.incrementAndGet(); return new FakeJedis(); }, new Clock())) {
        businessCalls.incrementAndGet();
        throw businessFailure;
      }
    }));
    assertEquals(1, calls.get());
    assertEquals(1, businessCalls.get());
  }

  @Test
  void cleanupFailureStopsRetryAndRetainsBothFailures() {
    var connection = new FakeJedis();
    var pingFailure = new JedisConnectionException("PING timeout");
    connection.reply = () -> { throw pingFailure; };
    connection.closeFailure = new IllegalStateException("close failure");
    var calls = new AtomicInteger();
    var failure = assertThrows(RedisLab.FixtureReadinessException.class,
        () -> ready(() -> { calls.incrementAndGet(); return connection; }, new Clock()));
    assertEquals(1, calls.get());
    assertEquals(1, connection.closes);
    assertSame(connection.closeFailure, failure.getCause());
    assertArrayEquals(new Throwable[] {pingFailure}, failure.getSuppressed());
  }

  @Test
  void interruptionDuringBackoffStopsAndPreservesInterruptFlag() {
    var calls = new AtomicInteger();
    try {
      var failure = assertThrows(RedisLab.FixtureReadinessException.class,
          () -> RedisLab.connectReady(PHASE,
              () -> { calls.incrementAndGet(); throw new JedisConnectionException("unavailable"); },
              Duration.ofSeconds(1), () -> 0L, nanos -> { throw new InterruptedException("cancelled"); }));
      assertTrue(Thread.currentThread().isInterrupted());
      assertInstanceOf(InterruptedException.class, failure.getCause());
      assertEquals(1, calls.get());
    } finally {
      Thread.interrupted();
    }
  }

  @Test
  void preexistingInterruptDoesNotOpenAnyConnection() {
    var calls = new AtomicInteger();
    try {
      Thread.currentThread().interrupt();
      assertThrows(RedisLab.FixtureReadinessException.class,
          () -> ready(() -> { calls.incrementAndGet(); return new FakeJedis(); }, new Clock()));
      assertTrue(Thread.currentThread().isInterrupted());
      assertEquals(0, calls.get());
    } finally {
      Thread.interrupted();
    }
  }

  @Test
  void invalidBudgetDoesNotOpenAnyConnection() {
    var calls = new AtomicInteger();
    assertThrows(IllegalArgumentException.class,
        () -> RedisLab.connectReady(PHASE,
            () -> { calls.incrementAndGet(); return new FakeJedis(); },
            Duration.ZERO, () -> 0L, nanos -> {}));
    assertEquals(0, calls.get());
  }
}
