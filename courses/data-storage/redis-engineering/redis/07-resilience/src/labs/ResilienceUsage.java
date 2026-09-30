package labs;

import java.time.Duration;
import java.util.Optional;
import labs.support.*;

public final class ResilienceUsage {
  public static void main(String[] args) {
    try (var lab = new RedisLab().start();
        var cache =
            new Resilience.RedisCache(lab.container.getHost(), lab.container.getMappedPort(6379));
        var service =
            new Resilience(cache, key -> Optional.of("订单读模型fixture"), 2, Duration.ofMillis(200))) {
      String key = lab.key("order:7");
      System.out.println(service.read(key));
      System.out.println(service.read(key));
      lab.crash();
      System.out.println("故障降级=" + service.read(key));
      lab.restart();
      System.out.println("恢复=" + service.read(key));
      System.out.println("指标=" + service.metrics());
      System.out.println("本调用端回源是固定fixture；真实MySQL联调在IntegrationTest中");
    }
  }
}
