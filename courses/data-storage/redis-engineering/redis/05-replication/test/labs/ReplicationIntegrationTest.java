package labs;

import static org.junit.jupiter.api.Assertions.*;

import labs.support.RedisLab;
import org.junit.jupiter.api.*;
import org.testcontainers.containers.Network;

@Tag("integration")
class ReplicationIntegrationTest {
  @Test
  void rdbSnapshotAndAofAlwaysHaveDifferentProcessCrashBoundaries() {
    try (var lab = new RedisLab("--save", "", "--appendonly", "no", "--dir", "/data").start()) {
      String k = lab.key("rdb");
      try (var j = lab.connect()) {
        j.set(k, "快照内");
        j.save();
        j.set(k, "快照后");
      }
      lab.crash();
      lab.restart();
      try (var j = lab.connect()) {
        assertEquals("快照内", j.get(k));
      }
    }
    try (var lab =
        new RedisLab(
                "--save", "", "--appendonly", "yes", "--appendfsync", "always", "--dir", "/data")
            .start()) {
      String k = lab.key("aof");
      try (var j = lab.connect()) {
        j.set(k, "已确认");
      }
      lab.crash();
      lab.restart();
      try (var j = lab.connect()) {
        assertEquals("已确认", j.get(k));
        assertEquals("1", Replication.info(j.info("persistence")).get("aof_enabled"));
      }
    }
  }

  @Test
  void twoNodeReplicationWaitAndManualFailover() {
    try (Network network = Network.newNetwork();
        var primary =
            new RedisLab(network, "c07-primary", "--save", "", "--appendonly", "no").start();
        var replica =
            new RedisLab(
                    network,
                    "c07-replica",
                    "--replicaof",
                    "c07-primary",
                    "6379",
                    "--save",
                    "",
                    "--appendonly",
                    "no")
                .start()) {
      RedisLab.await(
          "复制链路up",
          () -> {
            try (var r = replica.connect()) {
              return "up".equals(Replication.info(r.info("replication")).get("master_link_status"));
            }
          });
      String key = primary.key("replicated");
      try (var p = primary.connect()) {
        p.set(key, "写入已确认");
        assertEquals(1, p.waitReplicas(1, 5000), "WAIT在同一写连接等待副本确认");
      }
      try (var r = replica.connect()) {
        assertEquals("写入已确认", r.get(key));
      }
      primary.crash();
      try (var p = primary.connect()) {
        assertThrows(RuntimeException.class, p::ping);
      }
      try (var r = replica.connect()) {
        Replication.promoteIsolatedReplica(r);
        assertEquals("写入已确认", r.get(key));
        r.set(key, "提升后可写");
        assertEquals("提升后可写", r.get(key));
      }
      // 旧主保持停止直到容器销毁；不把两节点手工切换包装为自动高可用。
    }
  }
}
