package labs.capstone;

import static labs.capstone.Model.*;

import redis.clients.jedis.Jedis;

/** 缓存只加速查询，不参与扣库存和幂等判定；失败自动回源，TTL限制每次缓存写入的寿命，不保证相对数据库提交的陈旧上限。 */
public final class OrderCache {
    private final String host;
    private final int port;

    public OrderCache(String host, int port) {
        this.host = host;
        this.port = port;
    }

    private Jedis client() {
        return new Jedis(host, port, 150, 150);
    }

    public Order get(String id) {
        try (var c = client()) {
            String value = c.get("order:" + id);
            return value == null ? null : Json.read(value, Order.class);
        } catch (RuntimeException failure) {
            return null;
        }
    }

    public void put(Order order) {
        try (var c = client()) {
            c.setex("order:" + order.requestId(), 5, Json.write(order));
        } catch (RuntimeException ignored) {
            /* 缓存失效不改变已经提交的业务事实。 */
        }
    }

    public void invalidate(String id) {
        try (var c = client()) {
            c.del("order:" + id);
        } catch (RuntimeException ignored) {
            /* 每次写入的TTL为五秒，晚回填仍可能延长陈旧窗口；强一致查询走数据库。 */
        }
    }

    public boolean healthy() {
        try (var c = client()) {
            return "PONG".equals(c.ping());
        } catch (RuntimeException unavailable) {
            return false;
        }
    }
}
