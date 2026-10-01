package labs.distributed;

import java.time.Duration;
import java.util.Random;
import java.util.concurrent.atomic.AtomicInteger;
import labs.distributed.idempotency.RetryBudget;

public final class Usage {
  public static void main(String[] args) throws Exception {
    AtomicInteger calls = new AtomicInteger();
    var retry =
        new RetryBudget(3, Duration.ofSeconds(1), Duration.ofMillis(10), Duration.ofMillis(50));
    String result =
        retry.execute(
            true,
            remaining -> {
              System.out.println("本次剩余预算：" + remaining.toMillis() + "毫秒");
              if (calls.incrementAndGet() == 1) throw new RetryBudget.TransientFailure("受控只读故障");
              return "查询成功";
            },
            System::nanoTime,
            duration -> Thread.sleep(duration),
            new Random(42));
    System.out.println(result);
    System.out.println("持久化幂等请执行本节integrationTest，重试循环本身不保证业务只执行一次");
  }
}
