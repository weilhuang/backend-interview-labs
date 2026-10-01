import static org.junit.jupiter.api.Assertions.*;

import labs.messaging.*;

import org.apache.kafka.clients.producer.ProducerRecord;
import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;

import java.time.Duration;
import java.util.List;
import java.util.concurrent.TimeUnit;

@Tag("docker")
class BrokerTest {
    @Test
    void 相同事件在两种真实队列上的业务不变量一致() throws Exception {
        Event event = new Event("same", "o1", 1, 100);
        Lab kafkaEffects = new Lab();
        try (var kafka = KafkaSupport.broker()) {
            kafka.start();
            String topic = KafkaSupport.topic(kafka.getBootstrapServers(), 1);
            try (var consumer =
                            KafkaSupport.consumer(
                                    kafka.getBootstrapServers(), "对照组", "read_committed");
                    var producer = KafkaSupport.producer(kafka.getBootstrapServers())) {
                consumer.subscribe(List.of(topic));
                for (int n = 0; n < 2; n++)
                    producer.send(new ProducerRecord<>(topic, event.order(), event.encode()))
                            .get(15, TimeUnit.SECONDS);
                var records = KafkaSupport.read(consumer, 2, Duration.ofSeconds(30));
                assertEquals(2, records.size());
                records.forEach(record -> kafkaEffects.accept(Event.decode(record.value())));
            }
        }
        Lab rocketEffects = new Lab();
        try (var rocket = new RocketSupport()) {
            rocket.start();
            String topic = rocket.topic("NORMAL");
            try (var consumer = rocket.consumer(rocket.group(false), topic);
                    var producer = rocket.producer(topic)) {
                for (int n = 0; n < 2; n++) producer.send(RocketClient.message(topic, event));
                var records = RocketClient.receive(consumer, 2, Duration.ofSeconds(30));
                assertEquals(2, records.size());
                for (var record : records) {
                    rocketEffects.accept(RocketClient.event(record));
                    consumer.ack(record);
                }
            }
        }
        assertEquals(100, kafkaEffects.total());
        assertEquals(kafkaEffects.total(), rocketEffects.total());
    }
}
