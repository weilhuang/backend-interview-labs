package labs;

/** 容器内直接复用应用传输层诊断；无管理端口、不打印密码。 */
public final class RedisDiagnostic {
    public static void main(String[] args) {
        try {
            var env = System.getenv();
            var client = new RedisClient(AddressPolicy.host(env), AddressPolicy.port(env), env.getOrDefault("REDIS_PASSWORD", ""), 600);
            if (!"PONG".equals(client.command("PING"))) throw new RedisClient.Failure("PROTOCOL");
            System.out.println("{\"status\":\"PONG\",\"layer\":\"APPLICATION\"}");
        } catch (RedisClient.Failure e) {
            System.out.println("{\"error\":\"DEPENDENCY_UNAVAILABLE\",\"layer\":\"" + e.layer + "\"}");
            System.exit(1);
        }
    }
}
