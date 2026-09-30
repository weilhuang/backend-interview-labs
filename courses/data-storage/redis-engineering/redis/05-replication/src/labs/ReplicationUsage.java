package labs;

import labs.support.RedisLab;
import org.testcontainers.containers.Network;

public final class ReplicationUsage {
  public static void main(String[] args) {
    try (var net = Network.newNetwork();
        var p = new RedisLab(net, "c07-primary").start();
        var r = new RedisLab(net, "c07-replica", "--replicaof", "c07-primary", "6379").start()) {
      RedisLab.await(
          "复制连接",
          () -> {
            try (var j = r.connect()) {
              return "up".equals(Replication.info(j.info("replication")).get("master_link_status"));
            }
          });
      try (var j = p.connect()) {
        j.set(p.key("demo"), "已同步");
        System.out.println("确认副本数=" + j.waitReplicas(1, 5000));
      }
      p.crash();
      try (var j = r.connect()) {
        Replication.promoteIsolatedReplica(j);
        System.out.println("提升角色=" + Replication.info(j.info("replication")).get("role"));
      }
    }
  }
}
