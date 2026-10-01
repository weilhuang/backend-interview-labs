package labs.distributed;

import java.time.Duration;
import labs.distributed.dubbo.Lab;

public final class Usage {
  public static void main(String[] args) {
    try (var server = new Lab.Server(new Lab.Provider("提供者一"), "N/A");
        var client = new Lab.Client(server.address(), false)) {
      System.out.println(
          "真实Dubbo TCP结果：" + client.quote("book", "trace-example", Duration.ofSeconds(3), 1));
    } finally {
      org.apache.dubbo.rpc.model.FrameworkModel.destroyAll();
    }
  }
}
