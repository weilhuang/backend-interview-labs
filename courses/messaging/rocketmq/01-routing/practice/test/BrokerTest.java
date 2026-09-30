import static org.junit.jupiter.api.Assertions.*;

import labs.messaging.*;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;

import java.time.Duration;

@Tag("docker")
class BrokerTest {
    @Test
    void 两个消费组各自收到真实消息() throws Exception {
        try (var broker = new RocketSupport()) {
            broker.start();
            String topic = broker.topic("NORMAL");
            assertEquals(
                    java.util.Set.of(broker.endpoint()),
                    broker.routeEndpoints(topic),
                    "QueryRoute必须返回客户端可达的随机映射Proxy端点，不能返回容器内127.0.0.1:8081");
            try (var first = broker.consumer(broker.group(false), topic);
                    var second = broker.consumer(broker.group(false), topic);
                    var producer = broker.producer(topic)) {
                Event event = new Event("e1", "o1", 1, 100);
                var receipt = Lab.publish(producer, topic, event);
                var a = RocketClient.receive(first, 1, Duration.ofSeconds(30)).getFirst();
                var b = RocketClient.receive(second, 1, Duration.ofSeconds(30)).getFirst();
                assertEquals(receipt.getMessageId(), a.getMessageId());
                assertEquals(a.getMessageId(), b.getMessageId());
                assertEquals(event, RocketClient.event(a));
                assertEquals("order", a.getTag().orElseThrow());
                first.ack(a);
                second.ack(b);
            }
        }
    }
}
