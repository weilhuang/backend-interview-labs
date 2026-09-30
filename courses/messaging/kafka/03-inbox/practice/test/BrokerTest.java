import static org.junit.jupiter.api.Assertions.*;

import labs.messaging.*;

import org.apache.kafka.clients.producer.ProducerRecord;
import org.apache.kafka.common.TopicPartition;
import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import org.testcontainers.containers.MySQLContainer;

import java.time.Duration;
import java.util.List;
import java.util.concurrent.TimeUnit;

@Tag("docker")
class BrokerTest {
    @Test
    void 真实数据库提交后崩溃重放只生效一次() throws Exception {
        try (var broker = KafkaSupport.broker();
                var mysql = new MySQLContainer<>(Images.get("MYSQL_IMAGE"))) {
            broker.start();
            mysql.start();
            Inbox inbox = new Inbox(mysql.getJdbcUrl(), mysql.getUsername(), mysql.getPassword());
            inbox.initialize();
            String topic = KafkaSupport.topic(broker.getBootstrapServers(), 1);
            TopicPartition partition = new TopicPartition(topic, 0);
            try (var producer = KafkaSupport.producer(broker.getBootstrapServers())) {
                producer.send(
                                new ProducerRecord<>(
                                        topic, "o1", new Event("e1", "o1", 1, 100).encode()))
                        .get(15, TimeUnit.SECONDS);
            }
            for (FailurePoint point :
                    List.of(FailurePoint.BEFORE_EFFECT, FailurePoint.AFTER_EFFECT_BEFORE_OFFSET)) {
                try (var consumer =
                        KafkaSupport.consumer(
                                broker.getBootstrapServers(), "inbox组", "read_committed")) {
                    consumer.assign(List.of(partition));
                    var record = KafkaSupport.read(consumer, 1, Duration.ofSeconds(20)).getFirst();
                    assertEquals(0, record.offset(), "崩溃前没有提交位点");
                    assertThrows(
                            FailurePoint.SimulatedCrash.class,
                            () -> Lab.handle(consumer, record, inbox, point));
                    assertEquals(
                            point == FailurePoint.BEFORE_EFFECT ? 0 : 100, inbox.balance("o1"));
                }
            }
            try (var recovered =
                    KafkaSupport.consumer(
                            broker.getBootstrapServers(), "inbox组", "read_committed")) {
                recovered.assign(List.of(partition));
                var replay = KafkaSupport.read(recovered, 1, Duration.ofSeconds(20)).getFirst();
                Lab.handle(recovered, replay, inbox, FailurePoint.NONE);
                assertEquals(100, inbox.balance("o1"));
                assertEquals(
                        1,
                        recovered.committed(java.util.Set.of(partition)).get(partition).offset());
            }
        }
    }

    @Test
    void 真实MySQL事件和订单标识符区分大小写与尾空格() throws Exception {
        try (var mysql = new MySQLContainer<>(Images.get("MYSQL_IMAGE"))) {
            mysql.start();
            Inbox inbox = new Inbox(mysql.getJdbcUrl(), mysql.getUsername(), mysql.getPassword());
            inbox.initialize();
            var identifiers = List.of("Case", "case", "case ");
            for (int i = 0; i < identifiers.size(); i++) {
                var event = new Event(identifiers.get(i), "shared", i, (i + 1) * 100L);
                assertTrue(inbox.apply(event), "不同的事件ID不能误当重复");
                assertFalse(inbox.apply(event), "完全相同的事件仍需幂等");
            }
            assertEquals(600, inbox.balance("shared"));
            for (int i = 0; i < identifiers.size(); i++) {
                assertTrue(inbox.apply(new Event("order-event-" + i, identifiers.get(i), i, i + 1)));
                assertEquals(i + 1, inbox.balance(identifiers.get(i)), "订单身份不能合并");
            }
            try (var c = inbox.connection(); var st = c.createStatement()) {
                try (var rows = st.executeQuery("SELECT pad_attribute FROM information_schema.collations"
                        + " WHERE collation_name='utf8mb4_0900_bin'")) {
                    assertTrue(rows.next());
                    assertEquals("NO PAD", rows.getString(1));
                }
                for (String id : identifiers) {
                    try (var q = c.prepareStatement("INSERT INTO source_orders VALUES (?,1)");
                            var o = c.prepareStatement("INSERT INTO outbox(event_id,payload) VALUES (?,?)")) {
                        q.setString(1,id); q.executeUpdate();
                        o.setString(1,id); o.setString(2,"合成事件"); o.executeUpdate();
                    }
                }
                for (String table : List.of("source_orders","outbox")) {
                    try (var rows = st.executeQuery("SELECT COUNT(*) FROM " + table)) {
                        assertTrue(rows.next()); assertEquals(3, rows.getLong(1));
                    }
                }
            }
        }
    }

    @Test
    void 旧MySQL错误排序规则不能被IFNOTEXISTS静默沿用() throws Exception {
        try (var mysql = new MySQLContainer<>(Images.get("MYSQL_IMAGE"))) {
            mysql.start();
            Inbox inbox = new Inbox(mysql.getJdbcUrl(), mysql.getUsername(), mysql.getPassword());
            try (var c = inbox.connection(); var st = c.createStatement()) {
                st.execute("CREATE TABLE inbox (event_id VARCHAR(100) CHARACTER SET utf8mb4"
                        + " COLLATE utf8mb4_0900_ai_ci PRIMARY KEY)");
                st.execute("INSERT INTO inbox VALUES ('原有实验行')");
            }
            assertThrows(java.sql.SQLException.class, inbox::initialize);
            try (var c = inbox.connection(); var st = c.createStatement();
                    var rows = st.executeQuery("SELECT COUNT(*) FROM inbox")) {
                assertTrue(rows.next()); assertEquals(1, rows.getLong(1), "检测失败不得删除原数据");
            }
        }
    }
}
