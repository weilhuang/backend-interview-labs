package labs.distributed;

import static org.junit.jupiter.api.Assertions.*;

import java.time.Duration;
import labs.distributed.dubbo.Lab;
import org.junit.jupiter.api.*;

class DubboTest {
  @AfterAll
  static void 清理框架线程() {
    org.apache.dubbo.rpc.model.FrameworkModel.destroyAll();
  }

  @Test
  void 显式禁用本地调用后传递上下文与验证参数() {
    var provider = new Lab.Provider("p1");
    try (var server = new Lab.Server(provider, "N/A");
        var client = new Lab.Client(server.address(), false)) {
      String result = client.quote("book", "trace-1", Duration.ofSeconds(3), 1);
      assertTrue(result.startsWith("p1:book:trace-1:"));
      assertEquals(1, client.reserve("k1", "book", 1, "write", 2000));
      assertEquals(1, provider.writes.get());
      assertThrows(RuntimeException.class, () -> client.reserve("", "book", 1, "invalid", 2000));
      assertEquals(1, provider.writes.get());
      assertThrows(
          RuntimeException.class,
          () -> client.quote("book", "bad trace", Duration.ofSeconds(2), 1));
    }
  }

  @Test
  void 远程等待超时与上下文清理() {
    var provider = new Lab.Provider("slow");
    try (var server = new Lab.Server(provider, "N/A");
        var client = new Lab.Client(server.address(), false)) {
      client.quote("book", "warm", Duration.ofSeconds(3), 1);
      long start = System.nanoTime();
      try {
        assertThrows(
            RuntimeException.class,
            () -> client.quote("wait", "deadline", Duration.ofMillis(300), 1));
        assertTrue(System.nanoTime() - start < Duration.ofSeconds(2).toNanos());
        assertEquals(0, provider.waiting.getCount());
        assertNull(org.apache.dubbo.rpc.RpcContext.getClientAttachment().getAttachment("trace-id"));
      } finally {
        provider.release.countDown();
        org.apache.dubbo.rpc.RpcContext.removeClientAttachment();
      }
    }
  }

  @Test
  void 提供者退出后受总预算约束而不无限等待() {
    var server = new Lab.Server(new Lab.Provider("p2"), "N/A");
    try (var client = new Lab.Client(server.address(), false)) {
      client.quote("book", "warm", Duration.ofSeconds(3), 1);
      server.close();
      long started = System.nanoTime();
      assertThrows(
          RuntimeException.class, () -> client.quote("book", "failure", Duration.ofMillis(400), 2));
      assertTrue(System.nanoTime() - started < Duration.ofSeconds(3).toNanos());
    } finally {
      server.close();
    }
  }
}
