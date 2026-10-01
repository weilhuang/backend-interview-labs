import static org.junit.jupiter.api.Assertions.*;

import labs.messaging.*;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import org.testcontainers.containers.MySQLContainer;

import java.time.Duration;
import java.util.List;

@Tag("docker")
class BrokerTest {
    @Test
    void 发布确认窗口重放和毒消息隔离() throws Exception {
        try (var broker = KafkaSupport.broker();
                var mysql = new MySQLContainer<>(Images.get("MYSQL_IMAGE"))) {
            broker.start();
            mysql.start();
            Inbox database =
                    new Inbox(mysql.getJdbcUrl(), mysql.getUsername(), mysql.getPassword());
            database.initialize();
            Lab.enqueue(database, new Event("e1", "订单一", 1, 100));
            String topic = KafkaSupport.topic(broker.getBootstrapServers(), 1);
            String dlq = KafkaSupport.topic(broker.getBootstrapServers(), 1);
            try (var producer = KafkaSupport.producer(broker.getBootstrapServers());
                    var consumer =
                            KafkaSupport.consumer(
                                    broker.getBootstrapServers(), "恢复组", "read_committed");
                    var dead =
                            KafkaSupport.consumer(
                                    broker.getBootstrapServers(), "隔离组", "read_committed")) {
                assertThrows(
                        FailurePoint.SimulatedCrash.class,
                        () ->
                                Lab.publish(
                                        database,
                                        producer,
                                        topic,
                                        FailurePoint.AFTER_PUBLISH_BEFORE_MARK));
                Lab.publish(database, producer, topic, FailurePoint.NONE);
                consumer.subscribe(List.of(topic));
                var records = KafkaSupport.read(consumer, 2, Duration.ofSeconds(30));
                assertEquals(2, records.size());
                assertEquals(
                        1,
                        records.stream().map(r -> Event.decode(r.value()).id()).distinct().count());
                for (var record : records) database.apply(Event.decode(record.value()));
                assertEquals(100, database.balance("订单一"), "下游重复未累加；上游订单存放在source_orders");
                String poison = "未知格式";
                assertThrows(IllegalArgumentException.class, () -> Event.decode(poison));
                Lab.deadLetter(producer, dlq, poison, "永久格式错误");
                dead.subscribe(List.of(dlq));
                assertEquals(
                        "永久格式错误|未知格式",
                        KafkaSupport.read(dead, 1, Duration.ofSeconds(30)).getFirst().value());
            }
        }
    }
}
