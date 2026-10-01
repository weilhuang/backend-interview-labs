import static org.junit.jupiter.api.Assertions.*;

import labs.messaging.*;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;

import java.time.Duration;

@Tag("docker")
class BrokerTest {
    @Test
    void 实体顺序与延迟投递() throws Exception {
        try (var broker = new RocketSupport()) {
            broker.start();
            String ordered = broker.topic("FIFO");
            String delayed = broker.topic("DELAY");
            try (var consumer = broker.consumer(broker.group(true), ordered);
                    var timeout = broker.consumer(broker.group(false), delayed);
                    var producer =
                            RocketClient.PROVIDER
                                    .newProducerBuilder()
                                    .setClientConfiguration(broker.configuration())
                                    .setTopics(ordered, delayed)
                                    .build()) {
                for (int i = 1; i <= 3; i++)
                    producer.send(Lab.ordered(ordered, new Event("e" + i, "o1", i, 0)));
                for (int expected = 1; expected <= 3; expected++) {
                    var message =
                            RocketClient.receive(consumer, 1, Duration.ofSeconds(30)).getFirst();
                    assertEquals(expected, RocketClient.event(message).sequence());
                    consumer.ack(message);
                }
                long requested = ((System.currentTimeMillis() + 6999) / 1000) * 1000;
                producer.send(Lab.delayed(delayed, new Event("expire1", "o1", 4, 0), requested));
                var delivered = RocketClient.receive(timeout, 1, Duration.ofSeconds(45)).getFirst();
                assertEquals("expire1", RocketClient.event(delivered).id());
                assertTrue(System.currentTimeMillis() >= requested, "只约束不得早于计划时间，不保证准点执行业务");
                assertEquals(Lab.OrderState.PAID, Lab.cancelIfUnpaid(Lab.OrderState.PAID));
                timeout.ack(delivered);
            }
        }
    }
}
