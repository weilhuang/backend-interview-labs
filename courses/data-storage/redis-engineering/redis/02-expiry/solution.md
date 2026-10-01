# C07-02 公开标准解

完整参考实现如下，与src/labs/Expiry.java自动同步。逐步讲解、复杂度、边界和替代方案在题面。学习者可随时查看；独立回测建议换数据/故障点后重写。

```java
package labs;

import java.nio.charset.StandardCharsets;
import redis.clients.jedis.Jedis;
import redis.clients.jedis.params.SetParams;

/** 应用入口先限制单值字节数；maxmemory仍由服务端独立配置。 */
public final class Expiry {
  private final int maxBytes;

  public Expiry(int maxBytes) {
    if (maxBytes <= 0) throw new IllegalArgumentException("容量必须为正数");
    this.maxBytes = maxBytes;
  }

  public boolean put(Jedis redis, String key, String value, long ttlMillis) {
    // 学员实现开始
    if (value == null || ttlMillis <= 0) throw new IllegalArgumentException("值不能为空且有效期必须为正");
    if (value.getBytes(StandardCharsets.UTF_8).length > maxBytes) return false;
    redis.set(key, value, SetParams.setParams().px(ttlMillis));
    return true;
    // 学员实现结束
  }

  public record Observation(long ttlMillis, Long bytes, String encoding) {}

  public static Observation observe(Jedis redis, String key) {
    return new Observation(redis.pttl(key), redis.memoryUsage(key), redis.objectEncoding(key));
  }
}
```
