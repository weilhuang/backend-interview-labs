package labs.distributed;

import static org.junit.jupiter.api.Assertions.*;

import java.time.Duration;
import java.util.Random;
import java.util.concurrent.atomic.*;
import labs.distributed.idempotency.RetryBudget;
import org.junit.jupiter.api.Test;

class RetryTest {
  RetryBudget policy() {
    return new RetryBudget(3, Duration.ofMillis(100), Duration.ofMillis(10), Duration.ofMillis(40));
  }

  @Test
  void 暂时错误指数抖动并传递递减总预算() throws Exception {
    AtomicLong clock = new AtomicLong();
    AtomicInteger attempts = new AtomicInteger();
    java.util.List<Long> budgets = new java.util.ArrayList<>();
    String result =
        policy()
            .execute(
                true,
                remaining -> {
                  budgets.add(remaining.toNanos());
                  clock.addAndGet(10_000_000);
                  if (attempts.incrementAndGet() < 3)
                    throw new RetryBudget.TransientFailure("暂时失败");
                  return "成功";
                },
                clock::get,
                d -> clock.addAndGet(d.toNanos()),
                new Random(7));
    assertEquals("成功", result);
    assertEquals(3, attempts.get());
    assertTrue(budgets.get(0) > budgets.get(1) && budgets.get(1) > budgets.get(2));
  }

  @Test
  void 非幂等写及永久错误不重试() {
    AtomicInteger attempts = new AtomicInteger();
    assertThrows(
        RetryBudget.TransientFailure.class,
        () ->
            policy()
                .execute(
                    false,
                    left -> {
                      attempts.incrementAndGet();
                      throw new RetryBudget.TransientFailure("结果未知");
                    },
                    () -> 0,
                    d -> {},
                    new Random(1)));
    assertEquals(1, attempts.get());
    assertThrows(
        IllegalArgumentException.class,
        () ->
            policy()
                .execute(
                    true,
                    left -> {
                      throw new IllegalArgumentException("永久错误");
                    },
                    () -> 0,
                    d -> {},
                    new Random(1)));
  }

  @Test
  void 一次耗尽预算后不开始新尝试() {
    AtomicLong clock = new AtomicLong();
    AtomicInteger attempts = new AtomicInteger();
    assertThrows(
        RetryBudget.TransientFailure.class,
        () ->
            policy()
                .execute(
                    true,
                    left -> {
                      attempts.incrementAndGet();
                      clock.addAndGet(101_000_000);
                      throw new RetryBudget.TransientFailure("耗尽");
                    },
                    clock::get,
                    d -> fail("不能睡眠"),
                    new Random(2)));
    assertEquals(1, attempts.get());
  }
}
