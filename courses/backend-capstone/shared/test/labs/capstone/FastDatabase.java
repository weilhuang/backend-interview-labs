package labs.capstone;

import java.sql.*;
import java.util.UUID;

/** 仅验证控制流与事务回滚，不声称H2证明MySQL锁、排序规则或恢复。 */
final class FastDatabase {
    static Database open() throws SQLException {
        Database db =
                new Database(
                        "jdbc:h2:mem:" + UUID.randomUUID() + ";MODE=MySQL;DB_CLOSE_DELAY=-1",
                        "sa",
                        "");
        try (Connection c = db.open();
                Statement s = c.createStatement()) {
            s.execute(
                    "CREATE TABLE inventory(sku VARCHAR(100) PRIMARY KEY,initial_stock"
                        + " INT,available INT CHECK(available>=0 AND available<=initial_stock))");
            s.execute(
                    "CREATE TABLE orders(request_id VARCHAR(100) PRIMARY KEY,sku"
                        + " VARCHAR(100),quantity INT,status VARCHAR(16),version BIGINT)");
            s.execute(
                    "CREATE TABLE outbox(sequence_id BIGINT AUTO_INCREMENT PRIMARY KEY,event_id"
                        + " VARCHAR(100) UNIQUE,request_id VARCHAR(100),payload TEXT,published"
                        + " BOOLEAN DEFAULT FALSE)");
            s.execute("INSERT INTO inventory VALUES('book',20,20)");
        }
        return db;
    }
}
