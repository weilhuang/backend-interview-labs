import static org.junit.jupiter.api.Assertions.*;

import labs.messaging.*;

import org.apache.kafka.clients.producer.*;
import org.apache.kafka.common.TopicPartition;
import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;

import java.time.Duration;
import java.util.List;
import java.util.Set;
import java.util.concurrent.TimeUnit;

@Tag("docker")
class BrokerTest {
    @Test
    void 中止隔离与输出位点原子提交() throws Exception {
        try (var broker = KafkaSupport.broker()) {
            broker.start();
            String input = KafkaSupport.topic(broker.getBootstrapServers(), 1);
            String output = KafkaSupport.topic(broker.getBootstrapServers(), 1);
            var p = KafkaSupport.producerProperties(broker.getBootstrapServers());
            p.put(ProducerConfig.TRANSACTIONAL_ID_CONFIG, "流水线-" + input);
            try (var producer = new KafkaProducer<String, String>(p);
                    var seed = KafkaSupport.producer(broker.getBootstrapServers());
                    var consumer =
                            KafkaSupport.consumer(
                                    broker.getBootstrapServers(), "事务组", "read_committed")) {
                producer.initTransactions();
                seed.send(new ProducerRecord<>(input, "o1", "order-1")).get(15, TimeUnit.SECONDS);
                consumer.subscribe(List.of(input));
                var record = KafkaSupport.read(consumer, 1, Duration.ofSeconds(30)).getFirst();
                var partition = new TopicPartition(input, 0);
                Lab.transform(producer, consumer, record, output, true);
                assertNull(consumer.committed(Set.of(partition)).get(partition));
                consumer.seek(partition, record.offset());
                var replay = KafkaSupport.read(consumer, 1, Duration.ofSeconds(20)).getFirst();
                Lab.transform(producer, consumer, replay, output, false);
                assertEquals(1, consumer.committed(Set.of(partition)).get(partition).offset());
            }
            try (var committed =
                            KafkaSupport.consumer(
                                    broker.getBootstrapServers(), "读已提交", "read_committed");
                    var all =
                            KafkaSupport.consumer(
                                    broker.getBootstrapServers(), "读全部", "read_uncommitted")) {
                committed.subscribe(List.of(output));
                all.subscribe(List.of(output));
                var visible = KafkaSupport.read(committed, 1, Duration.ofSeconds(30));
                var unfiltered = KafkaSupport.read(all, 2, Duration.ofSeconds(30));
                assertEquals(1, visible.size());
                assertEquals("ORDER-1", visible.getFirst().value());
                assertEquals(2, unfiltered.size(), "普通读取能看见已中止事务的数据记录");
                assertTrue(committed.poll(Duration.ofSeconds(2)).isEmpty());
            }
        }
    }
}
