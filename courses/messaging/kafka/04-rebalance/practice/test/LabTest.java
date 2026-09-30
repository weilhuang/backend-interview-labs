import static org.junit.jupiter.api.Assertions.*;

import labs.messaging.Lab;

import org.apache.kafka.clients.consumer.MockConsumer;
import org.apache.kafka.clients.consumer.OffsetResetStrategy;
import org.apache.kafka.common.TopicPartition;
import org.junit.jupiter.api.Test;

import java.util.List;
import java.util.Set;

class LabTest {
    @Test
    void 已丢失分区不能保留可提交位点() {
        Lab listener = new Lab(null);
        var p = new TopicPartition("topic", 0);
        listener.completed(p, 7);
        listener.onPartitionsLost(List.of(p));
        assertTrue(listener.pending().isEmpty());
        assertEquals(20, Lab.lag(100, 80));
        assertThrows(IllegalArgumentException.class, () -> Lab.lag(80, 100));
    }

    @Test
    void 撤销只提交被撤销分区的完成位点() {
        try (var consumer = new MockConsumer<String, String>(OffsetResetStrategy.EARLIEST)) {
            var p0 = new TopicPartition("topic", 0);
            var p1 = new TopicPartition("topic", 1);
            consumer.assign(List.of(p0, p1));
            Lab listener = new Lab(consumer);
            listener.completed(p0, 7);
            listener.completed(p1, 3);
            listener.onPartitionsRevoked(List.of(p0));
            assertEquals(8, consumer.committed(Set.of(p0)).get(p0).offset());
            assertNull(consumer.committed(Set.of(p1)).get(p1));
            assertEquals(Set.of(p1), listener.pending().keySet());
        }
    }
}
