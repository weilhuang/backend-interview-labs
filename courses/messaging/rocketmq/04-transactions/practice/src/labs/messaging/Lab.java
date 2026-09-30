package labs.messaging;

import org.apache.rocketmq.client.apis.producer.TransactionResolution;

import java.sql.Connection;

/** 本地事务状态与订单行同事务持久化；回查从数据库事实恢复。 */
public final class Lab {
    public static void initialize(Inbox database) throws Exception {
        try (Connection c = database.connection();
                var statement = c.createStatement()) {
            String idType = Inbox.identifierSqlType(c);
            statement.execute("CREATE TABLE local_orders (event_id " + idType
                    + " PRIMARY KEY, cents BIGINT NOT NULL)");
            statement.execute("CREATE TABLE local_tx (event_id " + idType
                    + " PRIMARY KEY, state VARCHAR(20) NOT NULL)");
            Inbox.requireIdentifierCollation(c, "local_orders", "event_id");
            Inbox.requireIdentifierCollation(c, "local_tx", "event_id");
        }
    }

    public static void commitLocal(Inbox database, Event event) throws Exception {
        // 学习区开始
        try (Connection c = database.connection()) {
            c.setAutoCommit(false);
            try (var order = c.prepareStatement("INSERT INTO local_orders VALUES (?, ?)");
                    var status = c.prepareStatement("INSERT INTO local_tx VALUES (?, 'COMMIT')")) {
                order.setString(1, event.id());
                order.setLong(2, event.cents());
                order.executeUpdate();
                status.setString(1, event.id());
                status.executeUpdate();
                c.commit();
            } catch (Exception failure) {
                c.rollback();
                throw failure;
            }
        }
        // 学习区结束
    }

    public static TransactionResolution check(Inbox database, String id) {
        try (Connection c = database.connection();
                var query = c.prepareStatement("SELECT state FROM local_tx WHERE event_id=?")) {
            query.setString(1, id);
            try (var row = query.executeQuery()) {
                return row.next() ? resolution(row.getString(1)) : TransactionResolution.UNKNOWN;
            }
        } catch (Exception failure) {
            // 数据库不可用不是业务回滚的证据；让后续回查和人工恢复接管。
            return TransactionResolution.UNKNOWN;
        }
    }

    public static TransactionResolution resolution(String state) {
        return switch (state) {
            case "COMMIT" -> TransactionResolution.COMMIT;
            case "ROLLBACK" -> TransactionResolution.ROLLBACK;
            default -> TransactionResolution.UNKNOWN;
        };
    }
}
