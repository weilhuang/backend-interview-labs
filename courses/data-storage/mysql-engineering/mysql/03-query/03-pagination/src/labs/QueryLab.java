package labs;

import java.sql.*;
import java.time.Instant;
import java.util.*;

/** 游标包含完整排序键；这里只承诺同一稳定数据集内分页，不承诺跨请求全局快照。 */
public final class QueryLab {
    public record Cursor(Instant createdAt, long id) {
        public Cursor {
            Objects.requireNonNull(createdAt);
        }
    }

    private QueryLab() {}

    public static void validateLimit(int limit) {
        if (limit < 1 || limit > 100) throw new IllegalArgumentException("每页必须为 1 到 100 条");
    }

    public static List<Long> after(Connection c, long tenant, Cursor cursor, int limit)
            throws SQLException {
        validateLimit(limit);
        // BEGIN_STUDENT
        return Db.ids(
                c,
                "SELECT id FROM c06_orders WHERE tenant_id=? AND (created_at>? OR (created_at=? AND"
                        + " id>?)) ORDER BY created_at,id LIMIT ?",
                tenant,
                cursor.createdAt(),
                cursor.createdAt(),
                cursor.id(),
                limit);
        // END_STUDENT
    }

    public static List<Long> onUtcDay(Connection c, long tenant, Instant start)
            throws SQLException {
        if (start == null || !start.equals(start.truncatedTo(java.time.temporal.ChronoUnit.DAYS))) {
            throw new IllegalArgumentException("开始时刻必须是 UTC 零点");
        }
        return Db.ids(
                c,
                "SELECT id FROM c06_orders WHERE tenant_id=? AND created_at>=? AND created_at<?"
                        + " ORDER BY created_at,id",
                tenant,
                start,
                start.plusSeconds(86400));
    }

    public static List<Long> slowDay(Connection c, long tenant, String day) throws SQLException {
        return Db.ids(
                c,
                "SELECT id FROM c06_orders WHERE tenant_id=? AND DATE(created_at)=? ORDER BY"
                        + " created_at,id",
                tenant,
                day);
    }

    public static String plan(Connection c, String sql, Object... args) throws SQLException {
        return Db.text(c, "EXPLAIN ANALYZE " + sql, args);
    }
}
