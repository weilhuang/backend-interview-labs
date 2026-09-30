package labs;

import labs.support.RedisLab;

public final class StructuresUsage {
  public static void main(String[] args) {
    try (var lab = new RedisLab().start();
        var redis = lab.connect()) {
      String prefix = lab.key("demo:");
      Structures.seed(redis, prefix);
      System.out.println("会话用户=" + redis.hget(prefix + "session", "user"));
      System.out.println("窗口次数=" + Structures.incrementWithTtl(redis, prefix + "visits", 30_000));
      System.out.println(
          "去重订单数="
              + redis.scard(prefix + "seen")
              + "，排行榜="
              + redis.zrevrange(prefix + "rank", 0, -1));
    }
  }
}
