import static org.junit.jupiter.api.Assertions.*;

import labs.messaging.*;

import org.apache.kafka.clients.consumer.*;
import org.apache.kafka.common.TopicPartition;
import org.junit.jupiter.api.Test;

import java.util.List;
import java.util.Set;
import java.util.concurrent.atomic.AtomicInteger;

class LabTest {
    @Test
    void 业务成功后提交下一条位点() throws Exception {
        try (var consumer = new MockConsumer<String, String>(OffsetResetStrategy.EARLIEST)) {
            var partition = new TopicPartition("topic", 0);
            consumer.assign(List.of(partition));
            AtomicInteger effects = new AtomicInteger();
            var record =
                    new ConsumerRecord<>(
                            "topic", 0, 7, "o1", new Event("e1", "o1", 1, 100).encode());
            Lab.handle(consumer, record, event -> effects.incrementAndGet(), FailurePoint.NONE);
            assertEquals(1, effects.get());
            assertEquals(8, consumer.committed(Set.of(partition)).get(partition).offset());
        }
    }

    @Test
    void 两个窗口失败都不能提前提交() throws Exception {
        for (var point :
                List.of(FailurePoint.BEFORE_EFFECT, FailurePoint.AFTER_EFFECT_BEFORE_OFFSET)) {
            try (var consumer = new MockConsumer<String, String>(OffsetResetStrategy.EARLIEST)) {
                var partition = new TopicPartition("topic", 0);
                consumer.assign(List.of(partition));
                AtomicInteger effects = new AtomicInteger();
                var record =
                        new ConsumerRecord<>(
                                "topic", 0, 0, "o1", new Event("e1", "o1", 1, 100).encode());
                assertThrows(
                        FailurePoint.SimulatedCrash.class,
                        () ->
                                Lab.handle(
                                        consumer,
                                        record,
                                        event -> effects.incrementAndGet(),
                                        point));
                assertNull(consumer.committed(Set.of(partition)).get(partition));
                assertEquals(point == FailurePoint.BEFORE_EFFECT ? 0 : 1, effects.get());
            }
        }
    }
}
