package labs;

import java.time.Duration;
import java.util.Optional;
import labs.support.RedisLab;

public final class StampedeUsage {
  public static void main(String[] args) throws Exception {
    try (var lab = new RedisLab().start();
        var j = lab.connect()) {
      Stampede s = new Stampede(8, Duration.ofSeconds(1));
      String key = lab.key("unknown-order");
      for (int i = 0; i < 3; i++)
        System.out.println(
            "读取="
                + s.cached(
                    lab::connect,
                    key,
                    () -> {
                      System.out.println("仅首次回源");
                      return Optional.empty();
                    },
                    60_000,
                    3_000));
    }
  }
}
