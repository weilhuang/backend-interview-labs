package labs.capstone;

import static labs.capstone.Model.*;

import java.sql.*;

/** C14-02：请求身份、库存和outbox在一个MySQL事务中提交。 */
public final class OrderService {
    private final Database db;
    private final OrderCache cache;

    public OrderService(Database db, OrderCache cache) {
        this.db = db;
        this.cache = cache;
    }

    public Order place(Command command, Fault fault) throws SQLException {
        OrderRules.validate(command);
        Order result;
        // 学习区开始
        try (Connection c = db.open()) {
            c.setAutoCommit(false);
            try {
                // 先插入唯一请求身份。同一身份的并发请求会等待前一事务结束。
                try (PreparedStatement p =
                        c.prepareStatement("INSERT INTO orders VALUES(?,?,?,'RESERVED',1)")) {
                    p.setString(1, command.requestId());
                    p.setString(2, command.sku());
                    p.setInt(3, command.quantity());
                    p.executeUpdate();
                } catch (SQLException duplicate) {
                    if (duplicate.getErrorCode() != 1062) throw duplicate;
                    c.rollback();
                    Order existing = Database.readOrder(c, command.requestId(), true);
                    if (existing == null) throw duplicate;
                    result = OrderRules.sameRequest(existing, command);
                    c.commit();
                    return result;
                }
                try (PreparedStatement p =
                        c.prepareStatement(
                                "UPDATE inventory SET available=available-? WHERE sku=? AND"
                                    + " available>=?")) {
                    p.setInt(1, command.quantity());
                    p.setString(2, command.sku());
                    p.setInt(3, command.quantity());
                    if (p.executeUpdate() != 1) throw new Conflict("库存不足或商品不存在");
                }
                result =
                        new Order(
                                command.requestId(),
                                command.sku(),
                                command.quantity(),
                                "RESERVED",
                                1);
                append(c, Event.of(result));
                c.commit();
            } catch (SQLException | RuntimeException failure) {
                c.rollback();
                throw failure;
            }
        }
        // 学习区结束
        cache.invalidate(result.requestId());
        if (fault == Fault.AFTER_ORDER_COMMIT) throw new Unknown("数据库已提交但响应丢失；只能用原请求号查询或重试");
        return result;
    }

    public Order cancel(String id) throws SQLException {
        OrderRules.identifier(id, "请求号");
        Order result;
        // 学习区开始
        try (Connection c = db.open()) {
            c.setAutoCommit(false);
            try {
                Order current = Database.readOrder(c, id, true);
                if (current == null) throw new Conflict("订单不存在");
                if (!OrderRules.mayCancel(current.status())) {
                    c.commit();
                    return current;
                }
                try (PreparedStatement p =
                        c.prepareStatement(
                                "UPDATE inventory SET available=available+? WHERE sku=?")) {
                    p.setInt(1, current.quantity());
                    p.setString(2, current.sku());
                    p.executeUpdate();
                }
                try (PreparedStatement p =
                        c.prepareStatement(
                                "UPDATE orders SET status='CANCELLED',version=version+1 WHERE"
                                    + " request_id=?")) {
                    p.setString(1, id);
                    p.executeUpdate();
                }
                result = new Order(id, current.sku(), current.quantity(), "CANCELLED", 2);
                append(c, Event.of(result));
                c.commit();
            } catch (SQLException | RuntimeException failure) {
                c.rollback();
                throw failure;
            }
        }
        // 学习区结束
        cache.invalidate(id);
        return result;
    }

    static void append(Connection c, Event event) throws SQLException {
        try (PreparedStatement p =
                c.prepareStatement(
                        "INSERT INTO outbox(event_id,request_id,payload) VALUES(?,?,?)")) {
            p.setString(1, event.eventId());
            p.setString(2, event.requestId());
            p.setString(3, Json.write(event));
            p.executeUpdate();
        }
    }

    public Order find(String id, boolean fresh) throws SQLException {
        OrderRules.identifier(id, "请求号");
        if (!fresh) {
            Order hit = cache.get(id);
            if (hit != null) return hit;
        }
        try (Connection c = db.open()) {
            Order order = Database.readOrder(c, id, false);
            if (order != null && !fresh) cache.put(order);
            return order;
        }
    }
}
