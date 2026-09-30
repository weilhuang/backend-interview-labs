package labs;

import java.sql.*;
import java.util.*;

/** 订单查询保留租户边界，金额使用整数分；每个语句和结果集及时关闭。 */
public final class OrderQueries {
    private OrderQueries() {}

    public static long paidTotal(Connection c, long tenant) throws SQLException {
        // BEGIN_STUDENT
        return Db.scalar(
                c,
                "SELECT COALESCE(SUM(total_cents),0) FROM c06_orders WHERE tenant_id=? AND"
                    + " status='PAID'",
                tenant);
        // END_STUDENT
    }

    public static Map<Long, Long> quantities(Connection c, long tenant) throws SQLException {
        String sql =
                "SELECT i.sku,SUM(i.quantity) FROM c06_orders o JOIN c06_item i ON i.order_id=o.id"
                    + " WHERE o.tenant_id=? AND o.status='PAID' GROUP BY i.sku ORDER BY i.sku";
        try (PreparedStatement p = Db.prepare(c, sql, tenant);
                ResultSet r = p.executeQuery()) {
            Map<Long, Long> result = new LinkedHashMap<>();
            while (r.next()) result.put(r.getLong(1), r.getLong(2));
            return Collections.unmodifiableMap(result);
        }
    }

    public static long cents(String amount) {
        return new java.math.BigDecimal(amount).movePointRight(2).longValueExact();
    }
}
