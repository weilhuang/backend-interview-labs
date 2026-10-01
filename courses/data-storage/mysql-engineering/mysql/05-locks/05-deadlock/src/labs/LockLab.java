package labs;

import java.sql.*;

/** 只在明确死锁/锁等待错误上重试整个新事务；连接中断的提交结果可能未知。 */
public final class LockLab {
    private LockLab() {}

    public static boolean retryable(SQLException e) {
        // BEGIN_STUDENT
        return e.getErrorCode() == 1213 || e.getErrorCode() == 1205;
        // END_STUDENT
    }

    public static <T> T retry(Db.ConnectionFactory factory, int maxAttempts, Db.Work<T> work)
            throws SQLException {
        if (maxAttempts < 1 || maxAttempts > 5) throw new IllegalArgumentException("尝试次数必须为 1 到 5");
        for (int i = 1; ; i++)
            try (Connection c = factory.open()) {
                return Db.transaction(c, work);
            } catch (SQLException e) {
                if (i >= maxAttempts || !retryable(e)) throw e;
            }
    }

    public static void lockSku(Connection c, long sku) throws SQLException {
        Db.scalar(c, "SELECT quantity FROM c06_stock WHERE sku=? FOR UPDATE", sku);
    }

    public static void swapOne(Connection c, long from, long to) throws SQLException {
        if (from == to) throw new IllegalArgumentException("两个库存编号必须不同");
        // 全局按主键升序加锁，是本例消除相反顺序环路的办法。
        lockSku(c, Math.min(from, to));
        lockSku(c, Math.max(from, to));
        if (Db.update(
                        c,
                        "UPDATE c06_stock SET quantity=quantity-1 WHERE sku=? AND quantity>0",
                        from)
                != 1) throw new SQLException("源库存不足");
        Db.update(c, "UPDATE c06_stock SET quantity=quantity+1 WHERE sku=?", to);
    }
}
