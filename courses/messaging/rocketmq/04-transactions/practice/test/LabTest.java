import static org.junit.jupiter.api.Assertions.*;

import labs.messaging.*;

import org.apache.rocketmq.client.apis.producer.TransactionResolution;
import org.junit.jupiter.api.Test;

class LabTest {
    @Test
    void 三种事务状态不混淆() {
        assertEquals(TransactionResolution.COMMIT, Lab.resolution("COMMIT"));
        assertEquals(TransactionResolution.ROLLBACK, Lab.resolution("ROLLBACK"));
        assertEquals(TransactionResolution.UNKNOWN, Lab.resolution("不存在"));
        assertEquals(TransactionResolution.UNKNOWN, Lab.resolution("处理中"));
    }

    @Test
    void 本地事务成功状态与订单同时出现() throws Exception {
        Inbox db = database();
        Lab.commitLocal(db, new Event("e1", "o1", 1, 100));
        assertEquals(TransactionResolution.COMMIT, Lab.check(db, "e1"));
        assertEquals(TransactionResolution.UNKNOWN, Lab.check(db, "absent"));
        assertEquals(1, count(db, "e1"));
    }

    @Test
    void 写状态失败必须回滚先写的业务行() throws Exception {
        Inbox db = database();
        try (var connection = db.connection();
                var statement = connection.createStatement()) {
            statement.execute("INSERT INTO local_tx VALUES ('e1','ROLLBACK')");
        }
        assertThrows(Exception.class, () -> Lab.commitLocal(db, new Event("e1", "o1", 1, 100)));
        assertEquals(0, count(db, "e1"));
        assertEquals(TransactionResolution.ROLLBACK, Lab.check(db, "e1"));
    }

    private static Inbox database() throws Exception {
        // 嵌入式H2验证事务控制流；真实MySQL仍由BrokerTest验证。
        Inbox db =
                new Inbox(
                        "jdbc:h2:mem:"
                                + java.util.UUID.randomUUID()
                                + ";MODE=MySQL;DB_CLOSE_DELAY=-1",
                        "sa",
                        "");
        Lab.initialize(db);
        return db;
    }

    private static long count(Inbox db, String id) throws Exception {
        try (var connection = db.connection();
                var query =
                        connection.prepareStatement(
                                "SELECT COUNT(*) FROM local_orders WHERE event_id=?")) {
            query.setString(1, id);
            try (var rows = query.executeQuery()) {
                rows.next();
                return rows.getLong(1);
            }
        }
    }
}
