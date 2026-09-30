import static org.junit.jupiter.api.Assertions.*;

import labs.messaging.*;

import org.apache.kafka.clients.producer.MockProducer;
import org.apache.kafka.common.serialization.StringSerializer;
import org.junit.jupiter.api.Test;

import java.util.List;

class LabTest {
    @Test
    void 事件往返和非法字段() {
        Event event = new Event("evt-1", "order-1", 0, 100);
        assertEquals(event, Event.decode(event.encode()));
        assertThrows(IllegalArgumentException.class, () -> Event.decode("2|x|y|1|2"));
        assertThrows(IllegalArgumentException.class, () -> new Event("", "o", 0, 1));
    }

    @Test
    void 调用合同发送稳定订单键且保持输入顺序() throws Exception {
        // 官方MockProducer仅验证调用合同；实际分区保证由BrokerTest验证。
        try (var producer =
                new MockProducer<String, String>(
                        true, new StringSerializer(), new StringSerializer())) {
            var events = List.of(new Event("e1", "o1", 1, 100), new Event("e2", "o1", 2, 100));
            assertEquals(2, Lab.publish(producer, "topic", events).size());
            assertEquals(
                    List.of("o1", "o1"), producer.history().stream().map(r -> r.key()).toList());
            assertEquals(
                    events, producer.history().stream().map(r -> Event.decode(r.value())).toList());
            assertTrue(Lab.publish(producer, "topic", List.of()).isEmpty());
        }
    }
}
