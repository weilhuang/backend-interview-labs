package labs;

import static org.junit.jupiter.api.Assertions.*;

import java.util.concurrent.*;
import labs.support.*;
import org.junit.jupiter.api.*;

@Tag("integration")
class LeasesIntegrationTest {
  @Test
  void wrongOrExpiredOwnerCannotReleaseOrRenewAnotherLease() throws Exception {
    try (var lab = new RedisLab().start();
        var j = lab.connect()) {
      String key = lab.key("lease");
      var old = Leases.acquire(j, key, 30_000).orElseThrow();
      assertTrue(Leases.acquire(j, key, 30_000).isEmpty());
      assertFalse(Leases.release(j, new Leases.Lease(key, "impostor")));
      assertTrue(Leases.renew(j, old, 60_000));
      j.pexpire(key, 0);
      var next = Leases.acquire(j, key, 30_000).orElseThrow();
      assertNotEquals(old.token(), next.token());
      assertFalse(Leases.release(j, old));
      assertFalse(Leases.renew(j, old, 30_000));
      assertEquals(next.token(), j.get(key));
      assertTrue(Leases.release(j, next));
      CountDownLatch acquired = new CountDownLatch(1), cleaned = new CountDownLatch(1);
      try (var worker = Executors.newSingleThreadExecutor()) {
        var task =
            worker.submit(
                () -> {
                  try (var own = lab.connect()) {
                    var cancellable = Leases.acquire(own, key, 30_000).orElseThrow();
                    try {
                      acquired.countDown();
                      new CountDownLatch(1).await();
                    } catch (InterruptedException expected) {
                      Thread.currentThread().interrupt();
                    } finally {
                      try {
                        Leases.release(own, cancellable);
                      } finally {
                        cleaned.countDown();
                      }
                    }
                  }
                });
        try {
          assertTrue(acquired.await(3, TimeUnit.SECONDS));
          task.cancel(true);
          assertTrue(cleaned.await(3, TimeUnit.SECONDS));
        } finally {
          task.cancel(true);
        }
      }
      assertFalse(j.exists(key));
    }
  }

  @Test
  void counterexampleMintingFenceAfterLeaseAcquisitionIsUnsafe() throws Exception {
    try (var db = new MySqlLab().start();
        var lab = new RedisLab().start();
        var j = lab.connect()) {
      var resource = new Leases.FencedResource(db::connect);
      resource.initialize();
      String key = lab.key("unsafe-protocol");
      var paused = Leases.acquire(j, key, 30_000).orElseThrow(); // 反例：拿锁之后还没领序号就暂停。
      j.pexpire(key, 0);
      var current = Leases.acquireFenced(j, key, 30_000, resource).orElseThrow();
      assertTrue(resource.write(current.fence(), "合法新值"));
      long tooLate = resource.issueFence(); // 旧持有者恢复后错误地重新领号。
      assertTrue(resource.write(tooLate, "错误协议可覆盖"), "资源端仅看单调序号，无法修复错误的授予时序");
      assertFalse(Leases.release(j, paused));
      assertTrue(Leases.release(j, current.lease()));
    }
  }

  @Test
  void durableResourceRejectsPausedHolderAfterLeaseLoss() throws Exception {
    try (var db = new MySqlLab().start();
        var lab = new RedisLab().start();
        var j = lab.connect()) {
      var resource = new Leases.FencedResource(db::connect);
      resource.initialize();
      String key = lab.key("fenced");
      var oldFenced = Leases.acquireFenced(j, key, 30_000, resource).orElseThrow();
      var old = oldFenced.lease();
      long f1 = oldFenced.fence();
      j.pexpire(key, 0);
      var nextFenced = Leases.acquireFenced(j, key, 30_000, resource).orElseThrow();
      var next = nextFenced.lease();
      long f2 = nextFenced.fence();
      assertTrue(f2 > f1);
      assertTrue(resource.write(f2, "新持有者"));
      assertFalse(resource.write(f1, "暂停后复活的旧持有者"));
      assertFalse(resource.write(f2, "同令牌二次提交"), "本课契约是每fence一次写；不是每租约无限次写");
      assertEquals("新持有者", resource.value());
      assertFalse(Leases.release(j, old));
      assertTrue(Leases.release(j, next));
    }
  }
}
