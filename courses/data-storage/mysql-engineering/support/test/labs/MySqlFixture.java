package labs;

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

    static {
        MYSQL.start();
    }

    private MySqlFixture() {}

    public static Connection open() throws SQLException {
        return DriverManager.getConnection(
                MYSQL.getJdbcUrl()
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
