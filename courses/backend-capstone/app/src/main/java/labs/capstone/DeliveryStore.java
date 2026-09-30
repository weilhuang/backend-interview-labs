package labs.capstone;

import static labs.capstone.Model.*;

import java.sql.*;

/** 接收端独立事务：事件去重记录与业务读模型必须一起提交。 */
public final class DeliveryStore {
    private final Database db;

    public DeliveryStore(Database db) {
        this.db = db;
    }

    public boolean apply(Event event, Fault fault) throws SQLException {
        OrderRules.validateEvent(event);
        String payload = Json.write(event);
        try (Connection c = db.open()) {
            c.setAutoCommit(false);
            try {
                try (PreparedStatement p = c.prepareStatement("INSERT INTO inbox VALUES(?,?)")) {
                    p.setString(1, event.eventId());
                    p.setString(2, payload);
                    p.executeUpdate();
                } catch (SQLException duplicate) {
                    if (duplicate.getErrorCode() != 1062) throw duplicate;
                    c.rollback();
                    try (PreparedStatement p =
                            c.prepareStatement(
                                    "SELECT payload FROM inbox WHERE event_id=? FOR UPDATE")) {
                        p.setString(1, event.eventId());
                        try (ResultSet r = p.executeQuery()) {
                            if (!r.next() || !r.getString(1).equals(payload))
                                throw new Conflict("事件号重复但载荷不同");
                        }
                    }
                    c.commit();
                    return true;
                }
                // 唯一请求行充当版本锁；较旧消息只记去重，不倒退已取消状态。
                try (PreparedStatement p =
                        c.prepareStatement(
                                "INSERT INTO deliveries VALUES(?,?,?,?) ON DUPLICATE KEY UPDATE"
                                    + " request_id=request_id")) {
                    p.setString(1, event.requestId());
                    p.setString(2, event.eventId());
                    p.setString(3, event.status());
                    p.setLong(4, event.version());
                    p.executeUpdate();
                }
                try (PreparedStatement p =
                        c.prepareStatement(
                                "UPDATE deliveries SET event_id=?,status=?,version=? WHERE"
                                    + " request_id=? AND version<?")) {
                    p.setString(1, event.eventId());
                    p.setString(2, event.status());
                    p.setLong(3, event.version());
                    p.setString(4, event.requestId());
                    p.setLong(5, event.version());
                    p.executeUpdate();
                }
                c.commit();
            } catch (SQLException | RuntimeException failure) {
                c.rollback();
                throw failure;
            }
        }
        if (fault == Fault.AFTER_INBOX_COMMIT) throw new Unknown("投影已提交但RPC应答丢失");
        return false;
    }
}
