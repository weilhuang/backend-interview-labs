import static org.junit.jupiter.api.Assertions.*;

import labs.messaging.*;

import org.apache.kafka.clients.producer.MockProducer;
import org.apache.kafka.common.serialization.StringSerializer;
import org.junit.jupiter.api.Test;

class LabTest {
    @Test
    void 旧版本兼容与未知版本拒绝() {
        assertEquals(new Event("e1", "o1", 1, 100), Event.decode("1|e1|o1|1|100"));
        assertThrows(IllegalArgumentException.class, () -> Event.decode("2|e1|o1|1|100|新增字段"));
        assertThrows(NumberFormatException.class, () -> Event.decode("1|e1|o1|坏序号|100"));
    }

    @Test
    void 本地数据库确认窗口会重发() throws Exception {
        // H2只验证JDBC发布器控制流，真实MySQL语义与broker在BrokerTest中验证。
        Inbox db =
                new Inbox(
                        "jdbc:h2:mem:"
                                + java.util.UUID.randomUUID()
                                + ";MODE=MySQL;DB_CLOSE_DELAY=-1",
                        "sa",
                        "");
        db.initialize();
        Lab.enqueue(db, new Event("e1", "o1", 1, 100));
        try (var producer =
                new MockProducer<String, String>(
                        true, new StringSerializer(), new StringSerializer())) {
            assertThrows(
                    FailurePoint.SimulatedCrash.class,
                    () ->
                            Lab.publish(
                                    db, producer, "topic", FailurePoint.AFTER_PUBLISH_BEFORE_MARK));
            Lab.publish(db, producer, "topic", FailurePoint.NONE);
            Lab.publish(db, producer, "topic", FailurePoint.NONE);
            assertEquals(2, producer.history().size());
            assertEquals(producer.history().get(0).value(), producer.history().get(1).value());
        }
    }
}
