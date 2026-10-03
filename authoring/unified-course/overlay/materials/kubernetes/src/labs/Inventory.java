package labs;

/** 数据不放容器可写层：一个 Redis hash 保存库存与幂等记录。所有 key 显式传给 EVAL。 */
public final class Inventory {
    public static final String SEED = """
        -- academy:c11:seed:v1
        if redis.call('EXISTS', KEYS[1]) == 1 then return 0 end
        redis.call('HSET', KEYS[1], 'schema', '1', 'stock', '10')
        return 1
        """;
    public static final String RESERVE = """
        -- academy:c11:reserve:v1
        if redis.call('HGET', KEYS[1], 'schema') ~= '1' then return 'NOT_SEEDED' end
        local field = 'request:' .. ARGV[1]
        local old = redis.call('HGET', KEYS[1], field .. ':qty')
        if old then
          if old ~= ARGV[2] then return 'CONFLICT' end
          return 'REPLAY|' .. redis.call('HGET', KEYS[1], field .. ':remaining')
        end
        local stock = tonumber(redis.call('HGET', KEYS[1], 'stock'))
        local qty = tonumber(ARGV[2])
        if stock < qty then return 'SOLD_OUT' end
        local remaining = redis.call('HINCRBY', KEYS[1], 'stock', -qty)
        redis.call('HSET', KEYS[1], field .. ':qty', ARGV[2], field .. ':remaining', tostring(remaining))
        return 'CREATED|' .. tostring(remaining)
        """;
    private final RedisClient redis;
    private final String key;
    public Inventory(RedisClient redis, String namespace) {
        if (!namespace.matches("c11-[a-z0-9-]{1,48}")) throw new IllegalArgumentException("LAB_NAMESPACE must start c11-");
        this.redis = redis; key = namespace + ":inventory";
    }
    public boolean seeded() throws RedisClient.Failure { return "1".equals(redis.command("HGET", key, "schema")); }
    public boolean ping() throws RedisClient.Failure { return "PONG".equals(redis.command("PING")); }
    public boolean seed() throws RedisClient.Failure { return Long.valueOf(1).equals(redis.command("EVAL", SEED, "1", key)); }
    public int stock() throws RedisClient.Failure {
        Object result = redis.command("HGET", key, "stock");
        return result == null ? -1 : Integer.parseInt(result.toString());
    }
    public String reserve(String id, int quantity) throws RedisClient.Failure {
        return (String) redis.command("EVAL", RESERVE, "1", key, id, Integer.toString(quantity));
    }
}
