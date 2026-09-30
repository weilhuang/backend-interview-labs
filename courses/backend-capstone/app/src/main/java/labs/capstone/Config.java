package labs.capstone;

public record Config(
        String jdbc,
        String user,
        String password,
        String redisHost,
        int redisPort,
        String brokers,
        String rpcHost,
        int rpcPort) {
    private static String env(String key, String fallback) {
        return System.getenv().getOrDefault(key, fallback);
    }

    public static Config environment() {
        return new Config(
                env("LAB_JDBC", "jdbc:mysql://127.0.0.1:3307/capstone"),
                env("LAB_DB_USER", "lab"),
                env("LAB_DB_PASSWORD", "lab_only_password"),
                env("LAB_REDIS_HOST", "127.0.0.1"),
                Integer.parseInt(env("LAB_REDIS_PORT", "6380")),
                env("LAB_KAFKA", "127.0.0.1:9094"),
                env("LAB_RPC_HOST", "127.0.0.1"),
                Integer.parseInt(env("LAB_RPC_PORT", "9090")));
    }
}
