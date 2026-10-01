# C07-05 公开标准解

完整参考实现如下，与src/labs/Replication.java自动同步。逐步讲解、复杂度、边界和替代方案在题面。学习者可随时查看；独立回测建议换数据/故障点后重写。

```java
package labs;

import java.util.LinkedHashMap;
import java.util.Map;
import redis.clients.jedis.Jedis;

/** 操作两个隔离节点的手工故障转移；不实现Sentinel选举。 */
public final class Replication {
  private Replication() {}

  public static Map<String, String> info(String response) {
    Map<String, String> result = new LinkedHashMap<>();
    for (String line : response.split("\\r?\\n")) {
      if (line.isBlank() || line.startsWith("#")) continue;
      int p = line.indexOf(':');
      if (p > 0) result.put(line.substring(0, p), line.substring(p + 1));
    }
    return Map.copyOf(result);
  }

  /** 调用前必须隔离旧主；仅此命令不防止双主。 */
  public static void promoteIsolatedReplica(Jedis replica) {
    // 学员实现开始
    if (!"slave".equals(info(replica.info("replication")).get("role")))
      throw new IllegalStateException("目标必须先是副本");
    replica.replicaofNoOne();
    if (!"master".equals(info(replica.info("replication")).get("role")))
      throw new IllegalStateException("提升未生效");
    // 学员实现结束
  }
}
```
