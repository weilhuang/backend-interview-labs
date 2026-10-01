import static org.junit.jupiter.api.Assertions.*;

import labs.messaging.*;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;

import java.time.Duration;

@Tag("docker")
class BrokerTest {
    @Test
    void 未确认重投与真实隔离主题内容() throws Exception {
        try (var broker = new RocketSupport()) {
            broker.start();
            String topic = broker.topic("NORMAL");
            String dlq = broker.topic("NORMAL");
            try (var consumer = broker.consumer(broker.group(false), topic);
                    var dead = broker.consumer(broker.group(false), dlq);
                    var producer =
                            RocketClient.PROVIDER
                                    .newProducerBuilder()
                                    .setClientConfiguration(broker.configuration())
                                    .setTopics(topic, dlq)
                                    .build()) {
                producer.send(RocketClient.message(topic, new Event("e1", "o1", 1, 100)));
                var first = RocketClient.receive(consumer, 1, Duration.ofSeconds(30)).getFirst();
                // 不确认，等真实不可见期到期后由服务端重投；不是直接再次调用处理函数。
                var retry = RocketClient.receive(consumer, 1, Duration.ofSeconds(90)).getFirst();
                assertEquals(first.getMessageId(), retry.getMessageId());
                assertTrue(retry.getDeliveryAttempt() > first.getDeliveryAttempt());
                assertEquals(
                        Lab.Action.ACK,
                        Lab.decide(Lab.Failure.NONE, retry.getDeliveryAttempt(), 3));
                consumer.ack(retry);
                producer.send(RocketClient.message(topic, new Event("poison", "o2", 1, 0)));
                var poison = RocketClient.receive(consumer, 1, Duration.ofSeconds(30)).getFirst();
                Lab.quarantine(producer, consumer, poison, dlq);
                var isolated = RocketClient.receive(dead, 1, Duration.ofSeconds(30)).getFirst();
                assertEquals("poison", RocketClient.event(isolated).id());
                assertEquals(topic, isolated.getProperties().get("原始主题"));
                dead.ack(isolated);
            }
        }
    }
}
