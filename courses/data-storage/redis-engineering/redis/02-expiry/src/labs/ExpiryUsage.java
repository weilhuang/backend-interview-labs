package labs;

import labs.support.RedisLab;

public final class ExpiryUsage {
  public static void main(String[] args) {
    try (var lab = new RedisLab().start();
        var j = lab.connect()) {
      String key = lab.key("order");
      System.out.println("缓存成功=" + new Expiry(64).put(j, key, "订单已付款", 30_000));
      System.out.println("观测值=" + Expiry.observe(j, key));
      j.pexpire(key, 0);
      System.out.println("过期后=" + j.get(key));
    }
  }
}
