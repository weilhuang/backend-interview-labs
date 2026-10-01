package labs.capstone;

import static labs.capstone.Model.*;

import com.zaxxer.hikari.HikariConfig;
import com.zaxxer.hikari.HikariDataSource;

import java.sql.*;
import java.util.*;

/** 连接池预算是显式容量限制；订单与投影使用各自事务，绝不跨RPC持有数据库事务。 */
public final class Database implements AutoCloseable {
    private final HikariDataSource pool;

    public Database(String url, String user, String password) {
        HikariConfig config = new HikariConfig();
        config.setJdbcUrl(url);
        config.setUsername(user);
        config.setPassword(password);
        config.setMaximumPoolSize(8);
        config.setMinimumIdle(0);
        config.setConnectionTimeout(2000);
        config.setValidationTimeout(1000);
        config.setInitializationFailTimeout(-1);
        if (url.startsWith("jdbc:mysql:")) {
            config.addDataSourceProperty("connectTimeout", "2000");
            config.addDataSourceProperty("socketTimeout", "3000");
            config.addDataSourceProperty("tcpKeepAlive", "true");
        }
        pool = new HikariDataSource(config);
    }

    public Connection open() throws SQLException {
        return pool.getConnection();
    }

    public void initialize() throws SQLException {
        // 明确二进制、NO PAD身份；不会删除旧数据，也不会静默迁移不兼容旧表。
        try (Connection c = open();
                Statement s = c.createStatement()) {
            String id = "VARCHAR(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin";
            s.execute(
                    "CREATE TABLE IF NOT EXISTS inventory(sku "
                            + id
                            + " PRIMARY KEY, initial_stock INT NOT NULL, available INT NOT NULL,"
                            + " CHECK(available >= 0), CHECK(available <= initial_stock))"
                            + " ENGINE=InnoDB");
            s.execute(
                    "CREATE TABLE IF NOT EXISTS orders(request_id "
                            + id
                            + " PRIMARY KEY, sku "
                            + id
                            + " NOT NULL, quantity INT NOT NULL CHECK(quantity>0), status"
                            + " VARCHAR(16) NOT NULL, version BIGINT NOT NULL, INDEX"
                            + " orders_sku_status(sku,status)) ENGINE=InnoDB");
            s.execute(
                    "CREATE TABLE IF NOT EXISTS outbox(sequence_id BIGINT AUTO_INCREMENT PRIMARY"
                        + " KEY, event_id "
                            + id
                            + " NOT NULL UNIQUE, request_id "
                            + id
                            + " NOT NULL, payload TEXT NOT NULL, published BOOLEAN NOT NULL DEFAULT"
                            + " FALSE, INDEX outbox_pending(published,sequence_id)) ENGINE=InnoDB");
            s.execute(
                    "CREATE TABLE IF NOT EXISTS inbox(event_id "
                            + id
                            + " PRIMARY KEY, payload TEXT NOT NULL) ENGINE=InnoDB");
            s.execute(
                    "CREATE TABLE IF NOT EXISTS deliveries(request_id "
                            + id
                            + " PRIMARY KEY, event_id "
                            + id
                            + " NOT NULL, status VARCHAR(16) NOT NULL, version BIGINT NOT NULL)"
                            + " ENGINE=InnoDB");
            s.execute("INSERT IGNORE INTO inventory VALUES('book',20,20)");
            for (String spec :
                    List.of(
                            "inventory.sku",
                            "orders.request_id",
                            "orders.sku",
                            "outbox.event_id",
                            "outbox.request_id",
                            "inbox.event_id",
                            "deliveries.request_id",
                            "deliveries.event_id")) {
                String[] parts = spec.split("\\.");
                try (PreparedStatement p =
                        c.prepareStatement(
                                "SELECT COLLATION_NAME FROM information_schema.COLUMNS WHERE"
                                    + " TABLE_SCHEMA=DATABASE() AND TABLE_NAME=? AND"
                                    + " COLUMN_NAME=?")) {
                    p.setString(1, parts[0]);
                    p.setString(2, parts[1]);
                    try (ResultSet r = p.executeQuery()) {
                        if (!r.next() || !"utf8mb4_0900_bin".equals(r.getString(1)))
                            throw new SQLException("旧表身份排序规则不兼容：" + spec + "；请手工迁移并保留数据");
                    }
                }
            }
        }
    }

    public static Order readOrder(Connection c, String id, boolean lock) throws SQLException {
        try (PreparedStatement p =
                c.prepareStatement(
                        "SELECT request_id,sku,quantity,status,version FROM orders WHERE"
                            + " request_id=?"
                                + (lock ? " FOR UPDATE" : ""))) {
            p.setString(1, id);
            try (ResultSet r = p.executeQuery()) {
                return r.next()
                        ? new Order(
                                r.getString(1),
                                r.getString(2),
                                r.getInt(3),
                                r.getString(4),
                                r.getLong(5))
                        : null;
            }
        }
    }

    public long scalar(String query) throws SQLException {
        try (Connection c = open();
                Statement s = c.createStatement();
                ResultSet r = s.executeQuery(query)) {
            r.next();
            return r.getLong(1);
        }
    }

    public List<Order> orders() throws SQLException {
        var out = new ArrayList<Order>();
        try (Connection c = open();
                Statement s = c.createStatement();
                ResultSet r =
                        s.executeQuery(
                                "SELECT request_id,sku,quantity,status,version FROM orders ORDER BY"
                                    + " request_id")) {
            while (r.next())
                out.add(
                        new Order(
                                r.getString(1),
                                r.getString(2),
                                r.getInt(3),
                                r.getString(4),
                                r.getLong(5)));
        }
        return out;
    }

    public List<Stock> inventory() throws SQLException {
        var out = new ArrayList<Stock>();
        try (Connection c = open();
                Statement s = c.createStatement();
                ResultSet r =
                        s.executeQuery(
                                "SELECT sku,initial_stock,available FROM inventory ORDER BY sku")) {
            while (r.next()) out.add(new Stock(r.getString(1), r.getInt(2), r.getInt(3)));
        }
        return out;
    }

    public List<Delivery> deliveries() throws SQLException {
        var out = new ArrayList<Delivery>();
        try (Connection c = open();
                Statement s = c.createStatement();
                ResultSet r =
                        s.executeQuery(
                                "SELECT event_id,request_id,status,version FROM deliveries ORDER BY"
                                    + " request_id")) {
            while (r.next())
                out.add(new Delivery(r.getString(1), r.getString(2), r.getString(3), r.getLong(4)));
        }
        return out;
    }

    public record Snapshot(List<Stock> inventory, List<Order> orders, List<Delivery> deliveries) {}

    public Snapshot snapshot() throws SQLException {
        // 同一一致性快照避免把并发提交前后的两张表拼成伪造的库存错误。
        try (Connection c = open()) {
            c.setTransactionIsolation(Connection.TRANSACTION_REPEATABLE_READ);
            c.setReadOnly(true);
            c.setAutoCommit(false);
            var stocks = new ArrayList<Stock>();
            var orders = new ArrayList<Order>();
            var deliveries = new ArrayList<Delivery>();
            try (Statement s = c.createStatement();
                    ResultSet r =
                            s.executeQuery(
                                    "SELECT sku,initial_stock,available FROM inventory ORDER BY"
                                        + " sku")) {
                while (r.next()) stocks.add(new Stock(r.getString(1), r.getInt(2), r.getInt(3)));
            }
            try (Statement s = c.createStatement();
                    ResultSet r =
                            s.executeQuery(
                                    "SELECT request_id,sku,quantity,status,version FROM orders"
                                        + " ORDER BY request_id")) {
                while (r.next())
                    orders.add(
                            new Order(
                                    r.getString(1),
                                    r.getString(2),
                                    r.getInt(3),
                                    r.getString(4),
                                    r.getLong(5)));
            }
            try (Statement s = c.createStatement();
                    ResultSet r =
                            s.executeQuery(
                                    "SELECT event_id,request_id,status,version FROM deliveries"
                                        + " ORDER BY request_id")) {
                while (r.next())
                    deliveries.add(
                            new Delivery(
                                    r.getString(1), r.getString(2), r.getString(3), r.getLong(4)));
            }
            c.commit();
            return new Snapshot(List.copyOf(stocks), List.copyOf(orders), List.copyOf(deliveries));
        }
    }

    public void close() {
        pool.close();
    }
}
