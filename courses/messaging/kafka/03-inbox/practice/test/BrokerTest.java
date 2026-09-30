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
}
