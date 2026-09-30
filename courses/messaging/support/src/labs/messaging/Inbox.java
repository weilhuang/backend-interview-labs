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

    /** 标识符按精确字符序列比较；不使用自然语言的忽略大小写排序规则。 */
    public static String identifierSqlType(Connection c) throws SQLException {
        return switch (c.getMetaData().getDatabaseProductName()) {
            case "MySQL" -> "VARCHAR(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin";
            // H2只用于控制流单测，不能证明MySQL的排序规则与NO PAD语义。
            case "H2" -> "VARCHAR(100)";
            default -> throw new SQLException("本课程只声明MySQL与H2控制流环境");
        };
    }

    /** 老实验库不能凭IF NOT EXISTS沿用错误排序规则；只检查，不擅自迁移或删数据。 */
    public static void requireIdentifierCollation(Connection c, String table, String column)
            throws SQLException {
        if (!"MySQL".equals(c.getMetaData().getDatabaseProductName())) return;
        try (var p = c.prepareStatement(
                "SELECT collation_name FROM information_schema.columns WHERE table_schema=DATABASE()"
                        + " AND table_name=? AND column_name=?")) {
            p.setString(1, table);
            p.setString(2, column);
            try (var rows = p.executeQuery()) {
                if (!rows.next() || !"utf8mb4_0900_bin".equals(rows.getString(1))) {
                    throw new SQLException("实验标识符排序规则不兼容：" + table + "." + column
                            + "；请重建自己的隔离实验库，禁止自动迁移真实数据");
                }
            }
        }
    }

    public void initialize() throws SQLException {
        try (Connection c = connection();
                var s = c.createStatement()) {
            String idType = identifierSqlType(c);
            s.execute("CREATE TABLE IF NOT EXISTS inbox (event_id " + idType + " PRIMARY KEY)");
            s.execute("CREATE TABLE IF NOT EXISTS balances (order_id " + idType
                    + " PRIMARY KEY, cents BIGINT NOT NULL)");
            s.execute("CREATE TABLE IF NOT EXISTS source_orders (order_id " + idType
                    + " PRIMARY KEY, cents BIGINT NOT NULL)");
            s.execute("CREATE TABLE IF NOT EXISTS outbox (event_id " + idType
                    + " PRIMARY KEY, payload TEXT NOT NULL, sent BOOLEAN NOT NULL DEFAULT FALSE)");
            requireIdentifierCollation(c, "inbox", "event_id");
            requireIdentifierCollation(c, "balances", "order_id");
            requireIdentifierCollation(c, "source_orders", "order_id");
            requireIdentifierCollation(c, "outbox", "event_id");
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
