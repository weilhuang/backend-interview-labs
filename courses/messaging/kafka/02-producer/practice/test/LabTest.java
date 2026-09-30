import static org.junit.jupiter.api.Assertions.*;

import labs.messaging.Lab;

import org.apache.kafka.clients.producer.ProducerConfig;
import org.junit.jupiter.api.Test;

class LabTest {
    @Test
    void 可靠发送配置不能互相冲突() {
        var p = Lab.reliable("127.0.0.1:9092");
        assertEquals("all", p.getProperty(ProducerConfig.ACKS_CONFIG));
        assertEquals("true", p.getProperty(ProducerConfig.ENABLE_IDEMPOTENCE_CONFIG));
        assertTrue(
                Integer.parseInt(
                                p.getProperty(ProducerConfig.MAX_IN_FLIGHT_REQUESTS_PER_CONNECTION))
                        <= 5);
    }
}
