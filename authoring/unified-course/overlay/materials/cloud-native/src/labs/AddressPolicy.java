package labs;

import java.util.Map;

/** C11-03 的练习边界：连接容器服务名及容器端口，配置失败须明确报错。 */
public final class AddressPolicy {
    private AddressPolicy() {}
    public static String host(Map<String, String> env) {
        String host = env.getOrDefault("REDIS_HOST", "redis");
        if (host.isBlank() || host.contains("/") || host.contains(":")) {
            throw new IllegalArgumentException("REDIS_HOST must be a DNS name or IPv4 address");
        }
        return host;
    }
    public static int port(Map<String, String> env) {
        int port = Integer.parseInt(env.getOrDefault("REDIS_PORT", "6379"));
        if (port < 1 || port > 65535) throw new IllegalArgumentException("REDIS_PORT range");
        return port;
    }
}
