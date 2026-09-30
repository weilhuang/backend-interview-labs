package labs;

import static org.junit.jupiter.api.Assertions.*;

import java.time.Duration;
import java.util.Optional;
import labs.support.*;
import org.junit.jupiter.api.*;

@Tag("integration")
class ResilienceIntegrationTest {
  @Test
  void actualRedisOutageSlowResponseAndRecoveryWithActualMysqlOrigin() throws Exception {
    try (var db = new MySqlLab().start();
        var lab = new RedisLab().start()) {
      try (var c = db.connect();
          var s = c.createStatement()) {
        s.execute("CREATE TABLE order_view(id BIGINT PRIMARY KEY, value VARCHAR(100) NOT NULL)");
        s.execute("INSERT INTO order_view VALUES(7,'已付款')");
      }
      try (var cache =
              new Resilience.RedisCache(
                  lab.container.getHost(), lab.container.getMappedPort(6379));
          var service =
              new Resilience(
                  cache,
                  key -> {
                    try (var c = db.connect();
                        var s = c.prepareStatement("SELECT value FROM order_view WHERE id=?")) {
                      s.setQueryTimeout(1);
                      s.setLong(1, 7);
                      try (var r = s.executeQuery()) {
                        return r.next() ? Optional.of(r.getString(1)) : Optional.empty();
                      }
                    }
                  },
                  2,
                  Duration.ofSeconds(2))) {
        String key = lab.key("order:7");
        assertEquals(Resilience.Source.DATABASE, service.read(key).source());
        assertEquals(Resilience.Source.CACHE, service.read(key).source());
        // 服务端暂停所有命令；短socket超时应走受限回源，不使用大sleep等待结果。
        try (var control = lab.connect()) {
          control.clientPause(10_000);
          try {
            assertEquals(Resilience.Source.DATABASE, service.read(key).source());
            assertTrue(service.metrics().cacheErrors() > 0);
          } finally {
            control.clientUnpause();
          }
        }
        RedisLab.await(
            "暂停后恢复",
            () -> {
              try (var j = lab.connect()) {
                return "PONG".equals(j.ping());
              } catch (RuntimeException e) {
                return false;
              }
            });
        lab.crash();
        assertEquals(Resilience.Source.DATABASE, service.read(key).source());
        lab.restart();
        var recovered = service.read(key);
        assertTrue(
            recovered.source() == Resilience.Source.DATABASE
                || recovered.source() == Resilience.Source.CACHE);
        assertEquals("已付款", recovered.value().orElseThrow());
        assertEquals(Resilience.Source.CACHE, service.read(key).source());
        assertEquals(0, cache.activeConnections());
      }
    }
  }
}
