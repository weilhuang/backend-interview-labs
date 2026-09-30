package labs.messaging;

import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.SQLException;

/** MySQL 的去重记录和业务效果在同一事务中提交；本表只服务一个业务处理器。 */
public final class Inbox {
    private final String url;
    private final String user;
    private final String password;

    public Inbox(String url, String user, String password) {
        this.url = url;
        this.user = user;
        this.password = password;
    }

    public Connection connection() throws SQLException {
        var properties = new java.util.Properties();
        properties.setProperty("user", user);
        properties.setProperty("password", password);
        if (url.startsWith("jdbc:mysql:")) {
            // 回查和业务连接必须有界，依赖不可用时不能无限占用客户端线程。
            properties.setProperty("connectTimeout", "3000");
            properties.setProperty("socketTimeout", "5000");
        }
        return DriverManager.getConnection(url, properties);
    }

    public void initialize() throws SQLException {
        try (Connection c = connection();
                var s = c.createStatement()) {
            s.execute("CREATE TABLE IF NOT EXISTS inbox (event_id VARCHAR(100) PRIMARY KEY)");
            s.execute(
                    "CREATE TABLE IF NOT EXISTS balances (order_id VARCHAR(100) PRIMARY KEY, cents"
                            + " BIGINT NOT NULL)");
            s.execute(
                    "CREATE TABLE IF NOT EXISTS source_orders (order_id VARCHAR(100) PRIMARY KEY,"
                            + " cents BIGINT NOT NULL)");
            s.execute(
                    "CREATE TABLE IF NOT EXISTS outbox (event_id VARCHAR(100) PRIMARY KEY, payload"
                            + " TEXT NOT NULL, sent BOOLEAN NOT NULL DEFAULT FALSE)");
        }
    }

    public boolean apply(Event event) throws SQLException {
        try (Connection c = connection()) {
            c.setAutoCommit(false);
            try {
                try (var insert = c.prepareStatement("INSERT INTO inbox(event_id) VALUES (?)")) {
                    insert.setString(1, event.id());
                    insert.executeUpdate();
                }
                try (var update =
                        c.prepareStatement(
                                "INSERT INTO balances VALUES (?, ?) ON DUPLICATE KEY UPDATE"
                                        + " cents=cents+?")) {
                    update.setString(1, event.order());
                    update.setLong(2, event.cents());
                    update.setLong(3, event.cents());
                    update.executeUpdate();
                }
                c.commit();
                return true;
            } catch (SQLException failure) {
                c.rollback();
                if (failure.getErrorCode() == 1062) return false;
                throw failure;
            }
        }
    }

    public long balance(String order) throws SQLException {
        try (Connection c = connection();
                var q = c.prepareStatement("SELECT cents FROM balances WHERE order_id=?")) {
            q.setString(1, order);
            try (var r = q.executeQuery()) {
                return r.next() ? r.getLong(1) : 0;
            }
        }
    }
}
