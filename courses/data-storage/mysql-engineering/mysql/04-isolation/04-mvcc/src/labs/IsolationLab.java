package labs;

import java.sql.*;

/** 两个真实会话按代码顺序交错，不用线程随机调度或睡眠猜测快照建立时刻。 */
public final class IsolationLab {
    public record Trace(long first, long second, long locking) {}

    private IsolationLab() {}

    public static Trace observe(Connection reader, Connection writer, int isolation)
            throws SQLException {
        if (!reader.getAutoCommit() || !writer.getAutoCommit())
            throw new SQLException("实验需要两个空闲自动提交会话");
        int old = reader.getTransactionIsolation();
        reader.setTransactionIsolation(isolation);
        reader.setAutoCommit(false);
        Throwable primary = null;
        try {
            long first = Db.scalar(reader, "SELECT quantity FROM c06_stock WHERE sku=101");
            Db.update(writer, "UPDATE c06_stock SET quantity=quantity+1 WHERE sku=101");
            // BEGIN_STUDENT
            long second = Db.scalar(reader, "SELECT quantity FROM c06_stock WHERE sku=101");
            long locking =
                    Db.scalar(reader, "SELECT quantity FROM c06_stock WHERE sku=101 FOR UPDATE");
            return new Trace(first, second, locking);
            // END_STUDENT
        } catch (SQLException | RuntimeException | Error failure) {
            primary = failure;
            throw failure;
        } finally {
            SQLException cleanup = null;
            try {
                reader.rollback();
            } catch (SQLException failure) {
                cleanup = failure;
            }
            if (cleanup == null) {
                try {
                    reader.setAutoCommit(true);
                    reader.setTransactionIsolation(old);
                } catch (SQLException failure) {
                    cleanup = failure;
                }
            }
            if (cleanup != null) {
                // 回滚或会话复位失败后丢弃连接，不让下一位调用者承担未知状态。
                try {
                    reader.close();
                } catch (SQLException close) {
                    cleanup.addSuppressed(close);
                }
                if (primary != null) primary.addSuppressed(cleanup);
                else throw cleanup;
            }
        }
    }

    public static long expectedSecond(int isolation) {
        return switch (isolation) {
            case Connection.TRANSACTION_REPEATABLE_READ -> 10;
            case Connection.TRANSACTION_READ_COMMITTED -> 11;
            default -> throw new IllegalArgumentException("这里只研究 RC/RR");
        };
    }
}
