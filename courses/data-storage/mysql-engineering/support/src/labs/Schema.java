package labs;

import java.io.*;
import java.nio.charset.StandardCharsets;
import java.sql.*;

/** 只处理本课受控 SQL：语句以分号分隔，不支持存储过程或任意用户脚本。 */
public final class Schema {
    private Schema() {}

    public static void apply(Connection c, String resource) throws SQLException {
        if (!java.util.Set.of("schema.sql", "seed.sql", "reset.sql", "migration-v2.sql")
                .contains(resource)) throw new IllegalArgumentException("只允许课程内置脚本");
        try (InputStream in = Schema.class.getResourceAsStream("/" + resource)) {
            if (in == null) throw new IOException("找不到 SQL 资源");
            String sql =
                    new String(in.readAllBytes(), StandardCharsets.UTF_8)
                            .replaceAll("(?m)^--.*$", "");
            for (String statement : sql.split(";"))
                if (!statement.isBlank())
                    try (Statement s = c.createStatement()) {
                        s.execute(statement);
                    }
        } catch (IOException e) {
            throw new SQLException("读取课程 SQL 失败", e);
        }
    }

    public static void reset(Connection c) throws SQLException {
        // 不 DROP DATABASE、不关闭外键、不操作其他课程表；调用者必须显式选择实验库。
        apply(c, "schema.sql");
        if (Db.scalar(
                        c,
                        "SELECT COUNT(*) FROM information_schema.columns WHERE"
                            + " table_schema=DATABASE() AND table_name IN"
                            + " ('c06_orders','c06_reservation') AND column_name='request_id' AND"
                            + " collation_name <> 'utf8mb4_0900_bin'")
                > 0) {
            apply(c, "migration-v2.sql");
        }
        Db.transaction(
                c,
                tx -> {
                    apply(tx, "reset.sql");
                    apply(tx, "seed.sql");
                    return null;
                });
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 1 || !"--reset-c06-only".equals(args[0]))
            throw new IllegalArgumentException("重置只删除 c06_* 表数据；确认后传 --reset-c06-only");
        try (Connection c = Db.local()) {
            reset(c);
            System.out.println("已重建 c06_* 合成实验数据");
        }
    }
}
