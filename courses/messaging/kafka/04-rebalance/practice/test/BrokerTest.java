import static org.junit.jupiter.api.Assertions.*;

import labs.messaging.*;

import org.apache.kafka.clients.producer.ProducerRecord;
import org.apache.kafka.common.TopicPartition;
import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;

import java.time.Duration;
import java.util.HashSet;
import java.util.List;
import java.util.concurrent.TimeUnit;

@Tag("docker")
class BrokerTest {
    @Test
    void 扩实例后真实分区移交与积压计算() throws Exception {
        try (var broker = KafkaSupport.broker()) {
            broker.start();
            String topic = KafkaSupport.topic(broker.getBootstrapServers(), 2);
            try (var producer = KafkaSupport.producer(broker.getBootstrapServers());
                    var first =
                            KafkaSupport.consumer(
                                    broker.getBootstrapServers(), "扩容组", "read_committed");
                    var second =
                            KafkaSupport.consumer(
                                    broker.getBootstrapServers(), "扩容组", "read_committed")) {
                for (int p = 0; p < 2; p++)
                    for (int n = 0; n < 3; n++) {
                        producer.send(new ProducerRecord<>(topic, p, "o" + p, "消息" + n))
                                .get(15, TimeUnit.SECONDS);
                    }
                Lab listener = new Lab(first);
                first.subscribe(List.of(topic), listener);
                var records = KafkaSupport.read(first, 6, Duration.ofSeconds(30));
                records.forEach(
                        r ->
                                listener.completed(
                                        new TopicPartition(r.topic(), r.partition()), r.offset()));
                second.subscribe(List.of(topic), new Lab(second));
                long deadline = System.nanoTime() + Duration.ofSeconds(45).toNanos();
                do {
                    first.poll(Duration.ofMillis(100));
                    second.poll(Duration.ofMillis(100));
                } while ((first.assignment().size() != 1 || second.assignment().size() != 1)
                        && System.nanoTime() < deadline);
                assertEquals(1, first.assignment().size());
                assertEquals(1, second.assignment().size());
                var overlap = new HashSet<>(first.assignment());
                overlap.retainAll(second.assignment());
                assertTrue(overlap.isEmpty(), "稳定一代内每个分区只有一个所有者");
                assertTrue(listener.pending().isEmpty(), "撤销后本地位点已清空");
                var partition = second.assignment().iterator().next();
                long end = second.endOffsets(List.of(partition)).get(partition);
                long committed =
                        second.committed(java.util.Set.of(partition)).get(partition).offset();
                assertEquals(0, Lab.lag(end, committed));
            }
        }
    }
}
