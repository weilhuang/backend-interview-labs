package labs;

import java.nio.file.*;
import java.io.IOException;
import java.util.Map;

/** C11-05：不记录、不返回密码；环境配置是启动快照，公告文件是每次请求读取。 */
public record AppConfig(String redisHost, int redisPort, String redisPassword,
                        String namespace, String greeting, Path bannerFile,
                        long startupDelayMs, String release) {
    public static AppConfig load(Map<String,String> env) throws IOException {
        String host = env.getOrDefault("REDIS_HOST", "redis");
        if (!host.matches("[a-z0-9][a-z0-9.-]{0,250}") || host.equals("localhost") || host.equals("127.0.0.1"))
            throw new IllegalArgumentException("INVALID_REDIS_HOST");
        int port = Integer.parseInt(env.getOrDefault("REDIS_PORT", "6379"));
        if (port < 1 || port > 65535) throw new IllegalArgumentException("INVALID_REDIS_PORT");
        String password = Files.readString(Path.of(env.getOrDefault("REDIS_PASSWORD_FILE", "/run/secrets/password"))).strip();
        if (password.length() < 16 || password.length() > 128) throw new IllegalArgumentException("INVALID_SECRET_LENGTH");
        String greeting = safeLabel(env.getOrDefault("GREETING", "hello-v1"));
        long delay = Long.parseLong(env.getOrDefault("STARTUP_DELAY_MS", "8000"));
        if (delay < 0 || delay > 30000) throw new IllegalArgumentException("INVALID_STARTUP_DELAY");
        String release = safeLabel(Files.readString(Path.of(env.getOrDefault("RELEASE_FILE", "/opt/app/release"))).strip());
        String namespace = env.getOrDefault("LAB_NAMESPACE", "c11-kind-demo");
        if (!namespace.matches("c11-[a-z0-9-]{1,48}")) throw new IllegalArgumentException("INVALID_NAMESPACE");
        return new AppConfig(host, port, password, namespace, greeting,
                Path.of(env.getOrDefault("BANNER_FILE", "/etc/course/banner")), delay, release);
    }
    static String safeLabel(String value) {
        if (!value.matches("[a-zA-Z0-9_-]{1,40}")) throw new IllegalArgumentException("INVALID_PUBLIC_LABEL");
        return value;
    }
    public String banner() throws IOException { return safeLabel(Files.readString(bannerFile).strip()); }
    @Override public String toString() { return "AppConfig[redacted]"; }
}
