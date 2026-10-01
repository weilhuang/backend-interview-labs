package labs.distributed;

import static labs.distributed.grpc.RpcFailureObserver.call;
import static org.junit.jupiter.api.Assertions.*;

import java.util.UUID;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicBoolean;
import labs.distributed.capacity.*;
import labs.distributed.grpc.Lab;
import labs.distributed.grpc.RpcFailureObserver;
import labs.distributed.grpc.protocol.*;
import labs.distributed.support.Database;
import org.junit.jupiter.api.Test;

class CapacityTest {
  @Test
  void 容量估计拒绝错误输入且位布局不会静默溢出() {
    assertEquals(120, Admission.requiredConcurrency(1000, .08, 1.5));
    assertThrows(
        IllegalArgumentException.class, () -> Admission.requiredConcurrency(Double.NaN, 1, 1));
    assertNotEquals(IdLayout.compose(1, 1, 0), IdLayout.compose(1, 2, 0));
    assertNotEquals(IdLayout.compose(1, 1, 0), IdLayout.compose(1, 1, 1));
    assertThrows(IllegalArgumentException.class, () -> IdLayout.compose(-1, 0, 0));
    assertThrows(IllegalArgumentException.class, () -> IdLayout.compose(1, 1, 4096));
  }

  @Test
  void 入口无等待拒绝与异常许可归还() throws Exception {
    var admission = new Admission(1);
    CountDownLatch enteredOrFinished = new CountDownLatch(1);
    AtomicBoolean entered = new AtomicBoolean();
    CountDownLatch release = new CountDownLatch(1);
    try (var pool = Executors.newVirtualThreadPerTaskExecutor()) {
      var work =
          pool.submit(
              () -> {
                try {
                  return admission.execute(
                      () -> {
                        entered.set(true);
                        enteredOrFinished.countDown();
                        if (!release.await(3, TimeUnit.SECONDS))
                          throw new IllegalStateException("屏障超时");
                        return 1;
                      });
                } finally {
                  enteredOrFinished.countDown();
                }
              });
      try {
        assertTrue(enteredOrFinished.await(3, TimeUnit.SECONDS));
        // 工作线程提前失败时立即传播其真实cause，不能误报为进入屏障超时。
        if (!entered.get()) work.get(3, TimeUnit.SECONDS);
        assertTrue(entered.get());
        assertThrows(RejectedExecutionException.class, () -> admission.execute(() -> 2));
      } finally {
        release.countDown();
      }
      assertEquals(1, work.get(3, TimeUnit.SECONDS));
    }
    assertThrows(
        IllegalStateException.class,
        () ->
            admission.execute(
                () -> {
                  throw new IllegalStateException("失败");
                }));
    assertEquals(0, admission.active());
    assertEquals(1, admission.peak());
    assertEquals(3, admission.execute(() -> 3));
  }

  @Test
  void 网络与SQL合同烟测同键重放只扣一次() throws Exception {
    var db =
        new Database(
            "jdbc:h2:mem:" + UUID.randomUUID() + ";MODE=MySQL;DB_CLOSE_DELAY=-1", "sa", "");
    var backend = new DatabaseInventory(db, 2);
    backend.initialize(5);
    var failures = new RpcFailureObserver();
    try (var endpoint = new Lab.Endpoint(new Lab.Service(backend), failures)) {
      var request =
          ReserveRequest.newBuilder().setKey("order1").setSku("book").setQuantity(2).build();
      assertEquals(
          3,
          call(() ->
                  Lab.client(endpoint.channel, "first", 3000)
                      .withInterceptors(failures)
                      .reserve(request))
              .getAvailable());
      assertEquals(
          3,
          call(() ->
                  Lab.client(endpoint.channel, "retry", 3000)
                      .withInterceptors(failures)
                      .reserve(request))
              .getAvailable());
      assertEquals(3, db.scalar("SELECT available FROM inventory"));
      assertEquals(0, backend.admission.active());
    }
  }

  @Test
  void 两种真实RPC共享SQL幂等合同() throws Exception {
    var db =
        new Database(
            "jdbc:h2:mem:" + UUID.randomUUID() + ";MODE=MySQL;DB_CLOSE_DELAY=-1", "sa", "");
    var backend = new DatabaseInventory(db, 2);
    backend.initialize(6);
    var provider =
        new labs.distributed.dubbo.Lab.Provider("sql-fixture", new DubboDatabaseInventory(backend));
    var failures = new RpcFailureObserver();
    try (var server = new labs.distributed.dubbo.Lab.Server(provider, "N/A");
        var client = new labs.distributed.dubbo.Lab.Client(server.address(), false);
        var grpc = new Lab.Endpoint(new Lab.Service(backend), failures)) {
      assertEquals(4, client.reserve("shared-order", "book", 2, "dubbo", 3000));
      var request =
          ReserveRequest.newBuilder().setKey("shared-order").setSku("book").setQuantity(2).build();
      assertEquals(
          4,
          call(() ->
                  Lab.client(grpc.channel, "grpc", 3000)
                      .withInterceptors(failures)
                      .reserve(request))
              .getAvailable());
      assertEquals(4, db.scalar("SELECT available FROM inventory"));
    }
  }
}
