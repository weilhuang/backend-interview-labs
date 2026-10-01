import static org.junit.jupiter.api.Assertions.*;

import labs.messaging.*;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;

import java.time.Duration;
import java.util.List;

@Tag("docker")
class BrokerTest {
    @Test
    void 相同键路由和分区内顺序() throws Exception {
        try (var broker = KafkaSupport.broker()) {
            broker.start();
            String topic = KafkaSupport.topic(broker.getBootstrapServers(), 3);
            try (var producer = KafkaSupport.producer(broker.getBootstrapServers());
                    var consumer =
                            KafkaSupport.consumer(
                                    broker.getBootstrapServers(), "契约组", "read_committed")) {
                var metadata =
                        Lab.publish(
                                producer,
                                topic,
                                List.of(
                                        new Event("e1", "o1", 1, 100),
                                        new Event("e2", "o1", 2, 200),
                                        new Event("e3", "o1", 3, 300)));
                assertEquals(1, metadata.stream().map(m -> m.partition()).distinct().count());
                consumer.subscribe(List.of(topic));
                var records = KafkaSupport.read(consumer, 3, Duration.ofSeconds(30));
                assertEquals(
                        List.of(1L, 2L, 3L),
                        records.stream().map(r -> Event.decode(r.value()).sequence()).toList());
                assertEquals(3, consumer.assignment().size());
                assertEquals(List.of(0L, 1L, 2L), records.stream().map(r -> r.offset()).toList());
            }
        }
    }
}
