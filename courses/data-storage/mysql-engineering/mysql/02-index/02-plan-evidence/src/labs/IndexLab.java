package labs;

import java.sql.*;
import java.time.Instant;
import java.util.*;

/** EXPLAIN 为观察证据，优化器选择不作为跨机器固定断言。 */
public final class IndexLab {
    private IndexLab() {}

    public static final String QUERY =
            "SELECT id,created_at FROM c06_orders WHERE tenant_id=? AND status=? AND created_at>=?"
                + " ORDER BY created_at,id LIMIT 20";

    public static void addIndex(Connection c) throws SQLException {
        if (Db.scalar(
                        c,
                        "SELECT COUNT(*) FROM information_schema.statistics WHERE"
                            + " table_schema=DATABASE() AND table_name='c06_orders' AND"
                            + " index_name='idx_c06_feed'")
                == 0) {
            // BEGIN_STUDENT
            Db.update(c, "CREATE INDEX idx_c06_feed ON c06_orders(tenant_id,status,created_at,id)");
            // END_STUDENT
        }
    }

    public static void seedDistribution(Connection c, int n) throws SQLException {
        if (n < 1 || n > 100_000) throw new IllegalArgumentException("行数必须在 1 到 100000 之间");
        Db.transaction(
                c,
                tx -> {
                    try (PreparedStatement p =
                            Db.prepare(tx, "INSERT INTO c06_orders VALUES(?,?,?,?,?,?,?)")) {
                        for (int i = 1; i <= n; i++) {
                            p.setLong(1, 1000 + i);
                            p.setLong(2, i % 100 == 0 ? 8 : 7);
                            p.setString(3, "plan-" + i);
                            p.setLong(4, i % 100 == 0 ? 3 : 1);
                            p.setString(5, i % 4 == 0 ? "NEW" : "PAID");
                            p.setLong(6, 100);
                            p.setTimestamp(
                                    7,
                                    Timestamp.from(
                                            Instant.parse("2025-02-01T00:00:00Z").plusSeconds(i)));
                            p.addBatch();
                            if (i % 500 == 0) p.executeBatch();
                        }
                        p.executeBatch();
                    }
                    return null;
                });
        Db.text(c, "ANALYZE TABLE c06_orders");
    }

    public static String explain(Connection c, boolean execute) throws SQLException {
        return Db.text(
                c,
                (execute ? "EXPLAIN ANALYZE " : "EXPLAIN FORMAT=JSON ") + QUERY,
                7,
                "PAID",
                Instant.parse("2025-01-01T00:00:00Z"));
    }

    public static List<Long> result(Connection c) throws SQLException {
        return Db.ids(c, QUERY, 7, "PAID", Instant.parse("2025-01-01T00:00:00Z"));
    }
}
