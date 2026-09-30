package labs.distributed;

import labs.distributed.grpc.Lab;
import labs.distributed.grpc.protocol.QuoteRequest;

public final class Usage {
  public static void main(String[] args) throws Exception {
    Lab.Backend fixture =
        new Lab.Backend() {
          public int quote(String sku) {
            return 10;
          }

          public int reserve(String key, String sku, int quantity) {
            throw new IllegalStateException("只读调用示例，持久化写入在综合单元");
          }
        };
    try (var endpoint = new Lab.Endpoint(new Lab.Service(fixture))) {
      var reply =
          Lab.client(endpoint.channel, "trace-example", 3000)
              .quote(QuoteRequest.newBuilder().setSku("sku-1").build());
      System.out.println(
          "真实TCP端口="
              + endpoint.port()
              + " 库存="
              + reply.getAvailable()
              + " 追踪="
              + reply.getTraceId()
              + " 剩余预算="
              + reply.getRemainingMillis());
    }
  }
}
