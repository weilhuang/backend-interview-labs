package labs;

import static org.junit.jupiter.api.Assertions.*;

import labs.support.RedisLab;
import org.junit.jupiter.api.*;
import redis.clients.jedis.exceptions.JedisDataException;

@Tag("integration")
class ExpiryIntegrationTest {
  @Test
  void ttlMissingPersistentAndExplicitExpiryAreDifferent() {
    try (var lab = new RedisLab().start();
        var j = lab.connect()) {
      String k = lab.key("ttl");
      assertEquals(-2, j.pttl(k));
      j.set(k, "x");
      assertEquals(-1, j.pttl(k));
      assertTrue(new Expiry(20).put(j, k, "中文", 30_000));
      var observation = Expiry.observe(j, k);
      assertTrue(observation.ttlMillis() > 0 && observation.ttlMillis() <= 30_000);
      assertTrue(observation.bytes() > 0);
      j.pexpire(k, 0);
      assertNull(j.get(k));
      assertEquals(-2, j.pttl(k));
    }
  }

  @Test
  void noevictionRejectsAndAllkeysPolicyEvictsWithoutNamingVictim() {
    for (String policy : new String[] {"noeviction", "allkeys-lru"}) {
      try (var lab = new RedisLab("--maxmemory", "4mb", "--maxmemory-policy", policy).start();
          var j = lab.connect()) {
        boolean rejected = false;
        String value = "x".repeat(128 * 1024);
        for (int i = 0; i < 96; i++)
          try {
            j.set(lab.key("capacity:" + i), value);
          } catch (JedisDataException e) {
            assertTrue(e.getMessage().contains("OOM"));
            rejected = true;
            break;
          }
        if (policy.equals("noeviction")) assertTrue(rejected, "有界写入应触及4MB上限");
        else {
          assertFalse(rejected);
          assertTrue(metric(j.info("stats"), "evicted_keys") > 0);
        }
      }
    }
  }

  private static long metric(String info, String name) {
    return info.lines()
        .filter(s -> s.startsWith(name + ":"))
        .mapToLong(s -> Long.parseLong(s.substring(name.length() + 1).trim()))
        .findFirst()
        .orElseThrow();
  }
}
