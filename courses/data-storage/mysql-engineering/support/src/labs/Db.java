package labs;

import java.sql.*;
import java.time.Instant;
import java.util.*;

/** 真正 JDBC 封装；资源所有权明确，所有时间写入 UTC。不是数据库模拟器。 */
public final class Db {
    private Db() {}

    @FunctionalInterface
    public interface ConnectionFactory {
        Connection open() throws SQLException;
    }

    @FunctionalInterface
    public interface Work<T> {
        T run(Connection c) throws SQLException;
    }

    public static Connection local() throws SQLException {
        String url =
                System.getenv()
                        .getOrDefault(
                                "LAB_JDBC_URL",
                                "jdbc:mysql://127.0.0.1:13306/interview_lab?connectionTimeZone=UTC&forceConnectionTimeZoneToSession=true&connectTimeout=3000&socketTimeout=5000");
        String user = System.getenv().getOrDefault("LAB_DB_USER", "lab");
        String password = System.getenv("LAB_DB_PASSWORD");
        if (password == null) throw new SQLException("请设置 LAB_DB_PASSWORD 为本地实验密码；不要使用真实数据库");
        return DriverManager.getConnection(url, user, password);
    }

    public static <T> T transaction(Connection c, Work<T> work) throws SQLException {
        if (!c.getAutoCommit()) throw new SQLException("此入口只接收自动提交连接，避免意外提交调用方事务");
        c.setAutoCommit(false);
        Throwable primary = null;
        boolean rollbackFailed = false;
        try {
            T value = work.run(c);
            c.commit();
            return value;
        } catch (SQLException | RuntimeException | Error failure) {
            primary = failure;
            try {
                c.rollback();
            } catch (SQLException rollback) {
                failure.addSuppressed(rollback);
                rollbackFailed = true;
                // 回滚失败时不能开启自动提交，避免意外提交剩余工作；使连接退出可用状态。
                try {
                    c.close();
                } catch (SQLException close) {
                    failure.addSuppressed(close);
                }
            }
            throw failure;
        } finally {
            if (!rollbackFailed)
                try {
                    c.setAutoCommit(true);
                } catch (SQLException restore) {
                    if (primary != null) primary.addSuppressed(restore);
                    else throw restore;
                }
        }
    }

    public static PreparedStatement prepare(Connection c, String sql, Object... args)
            throws SQLException {
        PreparedStatement p = c.prepareStatement(sql);
        try {
            p.setQueryTimeout(5);
            for (int i = 0; i < args.length; i++) {
                Object value = args[i];
                if (value instanceof Instant t)
                    p.setTimestamp(
                            i + 1,
                            Timestamp.from(t),
                            Calendar.getInstance(TimeZone.getTimeZone("UTC")));
                else p.setObject(i + 1, value);
            }
            return p;
        } catch (SQLException | RuntimeException e) {
            p.close();
            throw e;
        }
    }

    public static int update(Connection c, String sql, Object... args) throws SQLException {
        try (PreparedStatement p = prepare(c, sql, args)) {
            return p.executeUpdate();
        }
    }

    public static long scalar(Connection c, String sql, Object... args) throws SQLException {
        try (PreparedStatement p = prepare(c, sql, args);
                ResultSet r = p.executeQuery()) {
            if (!r.next()) throw new SQLException("查询没有返回行");
            return r.getLong(1);
        }
    }

    public static List<Long> ids(Connection c, String sql, Object... args) throws SQLException {
        try (PreparedStatement p = prepare(c, sql, args);
                ResultSet r = p.executeQuery()) {
            List<Long> out = new ArrayList<>();
            while (r.next()) out.add(r.getLong(1));
            return List.copyOf(out);
        }
    }

    public static String text(Connection c, String sql, Object... args) throws SQLException {
        try (PreparedStatement p = prepare(c, sql, args);
                ResultSet r = p.executeQuery()) {
            StringBuilder b = new StringBuilder();
            while (r.next()) {
                b.append(r.getString(1)).append('\n');
            }
            return b.toString();
        }
    }
}
