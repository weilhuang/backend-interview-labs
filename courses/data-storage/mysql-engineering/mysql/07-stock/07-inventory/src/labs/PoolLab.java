package labs;

import com.zaxxer.hikari.HikariConfig;
import com.zaxxer.hikari.HikariDataSource;

/** 真实HikariCP连接池实验。借用超时、连接数与生命周期都有明确上限。 */
public final class PoolLab {
    private PoolLab() {}

    public static HikariDataSource create(String jdbc, String user, String password, int maximum) {
        if (maximum < 1 || maximum > 8) throw new IllegalArgumentException("教学连接池上限必须在1到8之间");
        HikariConfig config = new HikariConfig();
        config.setJdbcUrl(jdbc);
        config.setUsername(user);
        config.setPassword(password);
        config.setMaximumPoolSize(maximum);
        config.setMinimumIdle(0);
        config.setConnectionTimeout(300);
        config.setValidationTimeout(250);
        config.setPoolName("c06-实验连接池");
        config.setAutoCommit(true);
        return new HikariDataSource(config);
    }
}
