package labs;

import java.nio.charset.StandardCharsets;
import java.sql.*;
import java.util.Base64;
import java.util.List;
import redis.clients.jedis.Jedis;

/** 事务outbox + Redis版本水位。数据库才是事实来源；水位不随缓存TTL过期。 */
public final class Consistency {
  private Consistency() {}

  public record Product(long version, String value) {
    public Product {
      if (version < 1 || version > 9_007_199_254_740_991L || value == null)
        throw new IllegalArgumentException("版本必须在Lua整数精确范围内且值非空");
    }

    public String encoded() {
      return version
          + "|"
          + Base64.getEncoder().encodeToString(value.getBytes(StandardCharsets.UTF_8));
    }

    public static Product decode(String text) {
      int p = text.indexOf('|');
      if (p < 1) throw new IllegalArgumentException("缓存编码无效");
      return new Product(
          Long.parseLong(text.substring(0, p)),
          new String(Base64.getDecoder().decode(text.substring(p + 1)), StandardCharsets.UTF_8));
    }
  }

  @FunctionalInterface
  public interface Connections {
    Connection open() throws SQLException;
  }

  public static final class Store {
    private final Connections connections;

    public Store(Connections connections) {
      this.connections = connections;
    }

    public void initialize() throws SQLException {
      try (Connection c = connections.open();
          Statement s = c.createStatement()) {
        s.execute(
            "CREATE TABLE product (id BIGINT PRIMARY KEY, version BIGINT NOT NULL, value"
                + " VARCHAR(200) NOT NULL)");
        s.execute(
            "CREATE TABLE invalidation (event_id BIGINT AUTO_INCREMENT PRIMARY KEY, product_id"
                + " BIGINT NOT NULL, version BIGINT NOT NULL, delivered BOOLEAN NOT NULL DEFAULT"
                + " FALSE)");
        s.execute("INSERT INTO product VALUES(1,1,'旧价格')");
      }
    }

    public Product read(long id) throws SQLException {
      try (Connection c = connections.open();
          PreparedStatement s =
              c.prepareStatement("SELECT version,value FROM product WHERE id=?")) {
        s.setLong(1, id);
        s.setQueryTimeout(2);
        try (ResultSet r = s.executeQuery()) {
          if (!r.next()) throw new IllegalArgumentException("商品不存在");
          return new Product(r.getLong(1), r.getString(2));
        }
      }
    }

    public Product update(long id, String value) throws SQLException {
      return update(id, value, () -> {});
    }

    /** 故障回调用于在商品写入后、outbox写入前复现同事务中断。 */
    public Product update(long id, String value, Runnable afterProductWrite) throws SQLException {
      try (Connection c = connections.open()) {
        c.setAutoCommit(false);
        try {
          long version;
          try (PreparedStatement s =
              c.prepareStatement("SELECT version FROM product WHERE id=? FOR UPDATE")) {
            s.setLong(1, id);
            s.setQueryTimeout(2);
            try (ResultSet r = s.executeQuery()) {
              if (!r.next()) throw new IllegalArgumentException("商品不存在");
              version = Math.addExact(r.getLong(1), 1);
            }
          }
          Product result = new Product(version, value);
          try (PreparedStatement s =
              c.prepareStatement("UPDATE product SET version=?,value=? WHERE id=?")) {
            s.setLong(1, version);
            s.setString(2, value);
            s.setLong(3, id);
            s.executeUpdate();
          }
          afterProductWrite.run();
          try (PreparedStatement s =
              c.prepareStatement("INSERT INTO invalidation(product_id,version) VALUES(?,?)")) {
            s.setLong(1, id);
            s.setLong(2, version);
            s.executeUpdate();
          }
          c.commit();
          return result;
        } catch (SQLException | RuntimeException e) {
          labs.support.Transactions.rollback(c, e);
          throw e;
        }
      }
    }

    /** 同步最多处理limit个事件；发送后确认前崩溃会重发，Lua必须幂等。 */
    public int recover(Jedis redis, String prefix, int limit, Runnable afterSend)
        throws SQLException {
      if (limit < 1 || limit > 1000) throw new IllegalArgumentException("每批上限必须为1到1000");
      int count = 0;
      try (Connection c = connections.open();
          PreparedStatement s =
              c.prepareStatement(
                  "SELECT event_id,product_id,version FROM invalidation WHERE delivered=FALSE ORDER"
                      + " BY event_id LIMIT ?")) {
        s.setInt(1, limit);
        s.setQueryTimeout(2);
        try (ResultSet r = s.executeQuery()) {
          while (r.next()) {
            invalidate(redis, prefix, r.getLong(2), r.getLong(3));
            afterSend.run();
            try (PreparedStatement ack =
                c.prepareStatement("UPDATE invalidation SET delivered=TRUE WHERE event_id=?")) {
              ack.setLong(1, r.getLong(1));
              ack.executeUpdate();
            }
            count++;
          }
        }
      }
      return count;
    }

    /** 维护窗口内重建指定商品水位；完整系统必须分页遍历全部主键后才开放读流量。 */
    public void rebuildWatermark(Jedis redis, String prefix, long id) throws SQLException {
      Product current = read(id);
      invalidate(redis, prefix, id, current.version());
    }

    public long pending() throws SQLException {
      try (Connection c = connections.open();
          Statement s = c.createStatement();
          ResultSet r = s.executeQuery("SELECT COUNT(*) FROM invalidation WHERE delivered=FALSE")) {
        r.next();
        return r.getLong(1);
      }
    }
  }

  public static boolean fill(Jedis redis, String prefix, long id, Product product, long ttlMillis) {
    // 学员实现开始
    if (ttlMillis <= 0) throw new IllegalArgumentException("缓存TTL必须为正");
    Object accepted =
        redis.eval(
            """
            local floor=tonumber(redis.call('GET',KEYS[2]) or '0')
            local incoming=tonumber(ARGV[1])
            if incoming < floor then return 0 end
            local current=redis.call('GET',KEYS[1])
            if current and tonumber(string.match(current,'^(%d+)|')) > incoming then return 0 end
            redis.call('SET',KEYS[1],ARGV[2],'PX',ARGV[3])
            return 1
            """,
            List.of(key(prefix, id), watermark(prefix, id)),
            List.of(Long.toString(product.version()), product.encoded(), Long.toString(ttlMillis)));
    return ((Long) accepted) == 1;
    // 学员实现结束
  }

  public static void invalidate(Jedis redis, String prefix, long id, long version) {
    if (version < 1 || version > 9_007_199_254_740_991L)
      throw new IllegalArgumentException("水位版本越界");
    redis.eval(
        """
local floor=tonumber(redis.call('GET',KEYS[2]) or '0')
local incoming=tonumber(ARGV[1])
if incoming > floor then redis.call('SET',KEYS[2],ARGV[1]) end
local current=redis.call('GET',KEYS[1])
if current and tonumber(string.match(current,'^(%d+)|')) <= incoming then redis.call('DEL',KEYS[1]) end
return 1
""",
        List.of(key(prefix, id), watermark(prefix, id)), List.of(Long.toString(version)));
  }

  public static Product read(Store store, Jedis redis, String prefix, long id) throws SQLException {
    String hit = redis.get(key(prefix, id));
    if (hit != null) return Product.decode(hit);
    Product loaded = store.read(id);
    fill(redis, prefix, id, loaded, 30_000);
    return loaded;
  }

  public static String key(String prefix, long id) {
    return prefix + "product:{" + id + "}:value";
  }

  public static String watermark(String prefix, long id) {
    return prefix + "product:{" + id + "}:floor";
  }
}
