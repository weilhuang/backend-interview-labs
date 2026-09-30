package labs;

import java.sql.*;
import java.util.List;
import java.util.Optional;
import java.util.UUID;
import redis.clients.jedis.Jedis;
import redis.clients.jedis.params.SetParams;

/** 锁token只证明本次租约所有权；fence由持久资源端分配和验证。 */
public final class Leases {
  private Leases() {}

  public record Lease(String key, String token) {
    public Lease {
      if (key == null || token == null || token.isEmpty())
        throw new IllegalArgumentException("租约键与token不能为空");
    }
  }

  public static Optional<Lease> acquire(Jedis redis, String key, long ttlMillis) {
    validateTtl(ttlMillis);
    String token = UUID.randomUUID().toString();
    return "OK".equals(redis.set(key, token, SetParams.setParams().nx().px(ttlMillis)))
        ? Optional.of(new Lease(key, token))
        : Optional.empty();
  }

  public record FencedLease(Lease lease, long fence) {}

  /** 先领持久序号再获取租约；失败允许浪费序号，同一租约禁止重新领号。 */
  public static Optional<FencedLease> acquireFenced(
      Jedis redis, String key, long ttlMillis, FencedResource resource) throws SQLException {
    validateTtl(ttlMillis);
    long fence = resource.issueFence();
    return acquire(redis, key, ttlMillis).map(lease -> new FencedLease(lease, fence));
  }

  public static boolean release(Jedis redis, Lease lease) {
    // 学员实现开始
    return ((Long)
            redis.eval(
                "if redis.call('GET',KEYS[1]) == ARGV[1] then return redis.call('DEL',KEYS[1]) else"
                    + " return 0 end",
                List.of(lease.key()),
                List.of(lease.token())))
        == 1;
    // 学员实现结束
  }

  public static boolean renew(Jedis redis, Lease lease, long ttlMillis) {
    validateTtl(ttlMillis);
    return ((Long)
            redis.eval(
                "if redis.call('GET',KEYS[1]) == ARGV[1] then return"
                    + " redis.call('PEXPIRE',KEYS[1],ARGV[2]) else return 0 end",
                List.of(lease.key()),
                List.of(lease.token(), Long.toString(ttlMillis))))
        == 1;
  }

  private static void validateTtl(long ttlMillis) {
    if (ttlMillis <= 0) throw new IllegalArgumentException("租期必须为正");
  }

  @FunctionalInterface
  public interface Connections {
    Connection open() throws SQLException;
  }

  public static final class FencedResource {
    private final Connections connections;

    public FencedResource(Connections connections) {
      this.connections = connections;
    }

    public void initialize() throws SQLException {
      try (var c = connections.open();
          var s = c.createStatement()) {
        s.execute("CREATE TABLE fence_sequence (id INT PRIMARY KEY, value BIGINT NOT NULL)");
        s.execute("INSERT INTO fence_sequence VALUES(1,0)");
        s.execute(
            "CREATE TABLE protected_resource (id INT PRIMARY KEY, accepted_fence BIGINT NOT NULL,"
                + " value VARCHAR(200) NOT NULL)");
        s.execute("INSERT INTO protected_resource VALUES(1,0,'初始')");
      }
    }

    /** DB行锁序列不随Redis故障转移回退；授予后仍须资源端验证。 */
    public long issueFence() throws SQLException {
      try (var c = connections.open()) {
        c.setAutoCommit(false);
        try (var s = c.createStatement()) {
          s.setQueryTimeout(2);
          long next;
          try (var r = s.executeQuery("SELECT value FROM fence_sequence WHERE id=1 FOR UPDATE")) {
            r.next();
            next = Math.addExact(r.getLong(1), 1);
          }
          try (var update = c.prepareStatement("UPDATE fence_sequence SET value=? WHERE id=1")) {
            update.setLong(1, next);
            update.executeUpdate();
          }
          c.commit();
          return next;
        } catch (SQLException | RuntimeException e) {
          labs.support.Transactions.rollback(c, e);
          throw e;
        }
      }
    }

    public boolean write(long fence, String value) throws SQLException {
      if (fence <= 0 || value == null) throw new IllegalArgumentException("fence必须为正且值非空");
      try (var c = connections.open();
          var s =
              c.prepareStatement(
                  "UPDATE protected_resource SET accepted_fence=?,value=? WHERE id=1 AND"
                      + " accepted_fence<?")) {
        s.setQueryTimeout(2);
        s.setLong(1, fence);
        s.setString(2, value);
        s.setLong(3, fence);
        return s.executeUpdate() == 1;
      }
    }

    public String value() throws SQLException {
      try (var c = connections.open();
          var s = c.createStatement();
          var r = s.executeQuery("SELECT value FROM protected_resource WHERE id=1")) {
        r.next();
        return r.getString(1);
      }
    }
  }
}
