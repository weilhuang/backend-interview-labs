package labs;

import java.sql.*;
import java.util.concurrent.Semaphore;

/** 请求去重和扣库存写入同一事务。请求 ID 必须绑定参数，重复键不可掩盖参数冲突。 */
public final class StockLab {
    public enum Result {
        APPLIED,
        REPLAY,
        SOLD_OUT
    }

    private StockLab() {}

    public static Result reserve(Db.ConnectionFactory factory, String request, long sku, int amount)
            throws SQLException {
        if (request == null || request.isBlank() || request.length() > 80 || amount <= 0)
            throw new IllegalArgumentException("请求编号长度为 1 到 80，数量必须为正");
        try (Connection c = factory.open()) {
            try {
                return Db.transaction(
                        c,
                        tx -> {
                            Db.update(
                                    tx,
                                    "INSERT INTO c06_reservation(request_id,sku,quantity)"
                                        + " VALUES(?,?,?)",
                                    request,
                                    sku,
                                    amount);
                            // BEGIN_STUDENT
                            int changed =
                                    Db.update(
                                            tx,
                                            "UPDATE c06_stock SET"
                                                + " quantity=quantity-?,version=version+1 WHERE"
                                                + " sku=? AND quantity>=?",
                                            amount,
                                            sku,
                                            amount);
                            if (changed != 1) throw new SoldOut();
                            return Result.APPLIED;
                            // END_STUDENT
                        });
            } catch (SoldOut e) {
                return Result.SOLD_OUT;
            } catch (SQLException e) {
                if (e.getErrorCode() != 1062) throw e;
                try (PreparedStatement p =
                                Db.prepare(
                                        c,
                                        "SELECT sku,quantity FROM c06_reservation WHERE"
                                            + " request_id=?",
                                        request);
                        ResultSet r = p.executeQuery()) {
                    if (!r.next()) throw e;
                    if (r.getLong(1) != sku || r.getInt(2) != amount)
                        throw new IllegalArgumentException("同一个请求编号不能对应不同扣减参数");
                    return Result.REPLAY;
                }
            }
        }
    }

    private static final class SoldOut extends SQLException {}

    public static boolean optimistic(Connection c, long sku, long version, int amount)
            throws SQLException {
        if (amount <= 0) throw new IllegalArgumentException("数量必须为正");
        return Db.update(
                        c,
                        "UPDATE c06_stock SET quantity=quantity-?,version=version+1 WHERE sku=? AND"
                            + " version=? AND quantity>=?",
                        amount,
                        sku,
                        version,
                        amount)
                == 1;
    }

    /** 容量护栏是教学简化，不是连接池：真正池化还要处理连接健康与会话状态复位。 */
    public static final class Gate {
        private final Semaphore permits;

        public Gate(int n) {
            if (n < 1) throw new IllegalArgumentException("并发上限必须为正");
            permits = new Semaphore(n);
        }

        public <T> T run(Db.ConnectionFactory factory, Db.Work<T> work) throws SQLException {
            if (!permits.tryAcquire()) throw new SQLException("数据库并发预算已满");
            try (Connection c = factory.open()) {
                return work.run(c);
            } finally {
                permits.release();
            }
        }

        public int available() {
            return permits.availablePermits();
        }
    }
}
