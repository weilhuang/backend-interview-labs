import static org.junit.jupiter.api.Assertions.*;

import labs.messaging.*;

import org.apache.kafka.clients.producer.*;
import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;

import java.time.Duration;
import java.util.List;
import java.util.concurrent.TimeUnit;

@Tag("docker")
class BrokerTest {
    @Test
    void 幂等生产不会去掉业务重发() throws Exception {
        try (var broker = KafkaSupport.broker()) {
            broker.start();
            String topic = KafkaSupport.topic(broker.getBootstrapServers(), 1);
            try (var producer =
                            new KafkaProducer<String, String>(
                                    Lab.reliable(broker.getBootstrapServers()));
                    var consumer =
                            KafkaSupport.consumer(
                                    broker.getBootstrapServers(), "可靠性组", "read_committed")) {
                Event event = new Event("同一个业务标识", "订单一", 1, 100);
                for (int attempt = 0; attempt < 2; attempt++) {
                    producer.send(new ProducerRecord<>(topic, event.order(), event.encode()))
                            .get(15, TimeUnit.SECONDS);
                }
                consumer.subscribe(List.of(topic));
                var records = KafkaSupport.read(consumer, 2, Duration.ofSeconds(30));
                assertEquals(2, records.size(), "两次应用层 send 是两个合法序列号");
                assertEquals(records.get(0).value(), records.get(1).value());
                assertEquals(
                        1,
                        records.stream().map(r -> Event.decode(r.value()).id()).distinct().count());
                var invalid = Lab.reliable(broker.getBootstrapServers());
                invalid.put(ProducerConfig.ACKS_CONFIG, "0");
                assertThrows(
                        org.apache.kafka.common.config.ConfigException.class,
                        () -> new KafkaProducer<String, String>(invalid));
            }
        }
    }
}
