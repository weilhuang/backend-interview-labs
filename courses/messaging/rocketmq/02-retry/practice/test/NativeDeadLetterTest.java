import static org.junit.jupiter.api.Assertions.*;

import labs.messaging.*;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;

import java.time.Duration;

@Tag("docker")
class NativeDeadLetterTest {
    @Test
    void 消费组达到配置重试上限后进入真实原生死信队列() throws Exception {
        try (var broker = new RocketSupport()) {
            broker.start();
            String topic = broker.topic("NORMAL");
            String group = broker.group(false);
            broker.admin(
                    "updateSubGroup",
                    "-n",
                    "127.0.0.1:9876",
                    "-b",
                    "127.0.0.1:10911",
                    "-g",
                    group,
                    "-r",
                    "1",
                    "-p",
                    "{\"type\":\"CUSTOMIZED\",\"customizedRetryPolicy\":{\"next\":[1000]}}");
            String dlq = "%DLQ%" + group;
            // 只给本次随机课堂DLQ增加读取权限，方便公开管理工具验证原始消息体。
            broker.admin(
                    "updateTopic",
                    "-n",
                    "127.0.0.1:9876",
                    "-b",
                    "127.0.0.1:10911",
                    "-t",
                    dlq,
                    "-p",
                    "6",
                    "-r",
                    "1",
                    "-w",
                    "1");
            Event poison = new Event("native-poison", "o1", 1, 100);
            try (var consumer = broker.consumer(group, topic);
                    var producer = broker.producer(topic)) {
                producer.send(RocketClient.message(topic, poison));
                var first = RocketClient.receive(consumer, 1, Duration.ofSeconds(30)).getFirst();
                assertEquals(poison, RocketClient.event(first));
                String dump = "";
                long deadline = System.nanoTime() + Duration.ofSeconds(150).toNanos();
                do {
                    // 始终不确认，让服务端按真实重试上限转入DLQ；读取到的重投同样不确认。
                    consumer.receive(1, Duration.ofSeconds(10));
                    dump =
                            broker.admin(
                                    "printMsg", "-n", "127.0.0.1:9876", "-t", dlq, "-d", "true");
                } while (!dump.contains(poison.encode()) && System.nanoTime() < deadline);
                assertTrue(dump.contains(poison.encode()), "原生DLQ中应存在原始毒消息，实际：" + dump);
            }
        }
    }
}
