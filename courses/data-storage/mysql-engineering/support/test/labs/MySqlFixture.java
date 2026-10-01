package labs;

import com.github.dockerjava.api.model.ExposedPort;
import org.testcontainers.containers.MySQLContainer;
import org.testcontainers.utility.DockerImageName;

import java.sql.*;
import java.time.Duration;

/** 每个题目 JVM 独享容器，测试绝不连接真实服务；无 Docker 时应失败而非静默跳过。 */
public final class MySqlFixture {
    public static final MySQLContainer<?> MYSQL =
            new MySQLContainer<>(DockerImageName.parse(Images.mysql()))
                    .withDatabaseName("c06_lab")
                    .withUsername("lab")
                    .withPassword("synthetic_lab_only")
                    .withCommand(
                            "--log-bin=mysql-bin",
                            "--server-id=1",
                            "--sync-binlog=1",
                            "--innodb-flush-log-at-trx-commit=1",
                            "--innodb-lock-wait-timeout=2")
                    .withStartupTimeout(Duration.ofMinutes(3));

    private static volatile int mappedPort;

    static {
        MYSQL.start();
        mappedPort = MYSQL.getMappedPort(3306);
    }

    /** 同一容器重启后重新获取真实端口，不能把启动时的随机端口缓存视为永久不变。 */
    public static void refreshEndpoint() throws SQLException {
        try {
            var state = MYSQL.getDockerClient().inspectContainerCmd(MYSQL.getContainerId()).exec();
            var bindings = state.getNetworkSettings().getPorts().getBindings().get(ExposedPort.tcp(3306));
            if (bindings == null || bindings.length == 0) throw new SQLException("MySQL端口尚未重新发布");
            mappedPort = Integer.parseInt(bindings[0].getHostPortSpec());
        } catch (RuntimeException error) {
            throw new SQLException("无法读取恢复中容器的当前端口", error);
        }
    }

    private MySqlFixture() {}

    public static Connection open() throws SQLException {
        return DriverManager.getConnection(
                MYSQL.getJdbcUrl().replace(":" + MYSQL.getMappedPort(3306) + "/", ":" + mappedPort + "/")
                        + (MYSQL.getJdbcUrl().contains("?") ? "&" : "?")
                        + "connectionTimeZone=UTC&forceConnectionTimeZoneToSession=true&connectTimeout=3000&socketTimeout=8000",
                MYSQL.getUsername(),
                MYSQL.getPassword());
    }

    public static void reset() throws SQLException {
        try (Connection c = open()) {
            Schema.reset(c);
        }
    }
}
