package labs.distributed;

import static org.junit.jupiter.api.Assertions.*;

import io.grpc.*;
import java.util.concurrent.*;
import labs.distributed.capacity.*;
import labs.distributed.grpc.Lab;
import labs.distributed.grpc.protocol.*;
import labs.distributed.support.*;
import org.junit.jupiter.api.Test;

class InventoryIntegrationTest {
  @Test
  void 真实RPC和MySQL在并发下不超卖且重放结果稳定() throws Exception {
    try (var mysql = Images.mysql()) {
      mysql.start();
      var db = Images.database(mysql);
      var backend = new DatabaseInventory(db, 8);
      backend.initialize(10);
      try (var endpoint = new Lab.Endpoint(new Lab.Service(backend));
          var pool = Executors.newFixedThreadPool(8)) {
        Lab.client(endpoint.channel, "warm", 5000)
            .quote(QuoteRequest.newBuilder().setSku("book").build());
        var results =
            pool.invokeAll(
                java.util.stream.IntStream.range(0, 30)
                    .mapToObj(
                        i ->
                            (Callable<Boolean>)
                                () -> {
                                  var request =
                                      ReserveRequest.newBuilder()
                                          .setKey("order-" + i)
                                          .setSku("book")
                                          .setQuantity(1)
                                          .build();
                                  try {
                                    Lab.client(endpoint.channel, "load-" + i, 5000)
                                        .reserve(request);
                                    return true;
                                  } catch (StatusRuntimeException failure) {
                                    assertEquals(
                                        Status.Code.FAILED_PRECONDITION,
                                        failure.getStatus().getCode());
                                    return false;
                                  }
                                })
                    .toList());
        int successes = 0;
        for (var result : results) if (result.get(8, TimeUnit.SECONDS)) successes++;
        assertEquals(10, successes);
        assertEquals(0, db.scalar("SELECT available FROM inventory"));
        assertEquals(10, db.scalar("SELECT COUNT(*) FROM operations WHERE result>=0"));
        assertTrue(backend.admission.peak() <= 8);
        assertEquals(0, backend.admission.active());
        // 再调用一个成功键，返回原始结果而不是当前库存，也不产生第二次扣减。
        String key;
        try (var connection = db.open();
            var query = connection.createStatement();
            var rows =
                query.executeQuery("SELECT op_key FROM operations WHERE result>=0 LIMIT 1")) {
          rows.next();
          key = rows.getString(1);
        }
        var replay =
            Lab.client(endpoint.channel, "replay", 3000)
                .reserve(
                    ReserveRequest.newBuilder().setKey(key).setSku("book").setQuantity(1).build());
        assertTrue(replay.getAvailable() >= 0);
        assertEquals(0, db.scalar("SELECT available FROM inventory"));
      }
    }
  }

  @Test
  void Dubbo真实网络也使用持久化幂等业务合同() throws Exception {
    try (var mysql = Images.mysql()) {
      mysql.start();
      var db = Images.database(mysql);
      var backend = new DatabaseInventory(db, 4);
      backend.initialize(5);
      var provider =
          new labs.distributed.dubbo.Lab.Provider(
              "database-provider", new DubboDatabaseInventory(backend));
      try (var server = new labs.distributed.dubbo.Lab.Server(provider, "N/A");
          var client = new labs.distributed.dubbo.Lab.Client(server.address(), false)) {
        assertEquals(3, client.reserve("dubbo-order", "book", 2, "first", 3000));
        assertEquals(3, client.reserve("dubbo-order", "book", 2, "replay", 3000));
        assertEquals(3, db.scalar("SELECT available FROM inventory"));
        assertThrows(
            RuntimeException.class,
            () -> client.reserve("dubbo-order", "book", 3, "conflict", 3000));
        assertEquals(3, db.scalar("SELECT available FROM inventory"));
        assertEquals(0, backend.admission.active());
      }
    }
  }
}
