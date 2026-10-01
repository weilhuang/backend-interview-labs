package labs.distributed;

import static org.junit.jupiter.api.Assertions.*;

import java.time.Duration;
import java.util.HashSet;
import labs.distributed.dubbo.Lab;
import org.apache.curator.test.TestingServer;
import org.junit.jupiter.api.*;

// 提前关闭提供者是本测试故障注入，另一个资源仅用于维持可用节点。
@SuppressWarnings("try")
class DiscoveryTest {
  @AfterAll
  static void 清理框架线程() {
    org.apache.dubbo.rpc.model.FrameworkModel.destroyAll();
  }

  @Test
  void 真实注册中心发现两个提供者及故障摘除() throws Exception {
    try (var registry = new TestingServer()) {
      String address = "zookeeper://" + registry.getConnectString();
      try (var first = new Lab.Server(new Lab.Provider("first"), address);
          var second = new Lab.Server(new Lab.Provider("second"), address);
          var client = new Lab.Client(address, true)) {
        HashSet<String> providers = new HashSet<>();
        for (int i = 0; i < 12; i++)
          providers.add(client.quote("book", "discover", Duration.ofSeconds(3), 2).split(":")[0]);
        assertEquals(java.util.Set.of("first", "second"), providers);
        first.close();
        long end = System.nanoTime() + Duration.ofSeconds(8).toNanos();
        String result = "";
        while (System.nanoTime() < end) {
          try {
            result = client.quote("book", "after", Duration.ofSeconds(1), 2);
          } catch (RuntimeException temporary) {
            java.util.concurrent.locks.LockSupport.parkNanos(20_000_000);
            continue;
          }
          if (result.startsWith("second:")) break;
        }
        assertTrue(result.startsWith("second:"));
      }
    }
  }
}
