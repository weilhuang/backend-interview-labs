import static org.junit.jupiter.api.Assertions.*;

import labs.messaging.*;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;

import java.time.Duration;

@Tag("docker")
class BrokerTest {
    @Test
    void 同步刷盘配置下容器重启保留已确认消息() throws Exception {
        try (var broker = new RocketSupport()) {
            broker.start();
            String topic = broker.topic("NORMAL");
            String group = broker.group(false);
            try (var ready = broker.consumer(group, topic);
                    var producer = broker.producer(topic)) {
                producer.send(RocketClient.message(topic, new Event("disk1", "o1", 1, 100)));
            }
            var files =
                    broker.execInContainer(
                            "sh", "-c", "find /home/rocketmq/store -maxdepth 2 -type f | head -20");
            assertEquals(0, files.getExitCode());
            assertTrue(files.getStdout().contains("commitlog"), "应该观察到真实CommitLog文件");
            broker.getDockerClient()
                    .restartContainerCmd(broker.getContainerId())
                    .withTimeout(5)
                    .exec();
            org.testcontainers.containers.wait.strategy.Wait.forListeningPort()
                    .withStartupTimeout(Duration.ofMinutes(2))
                    .waitUntilReady(broker);
            broker.admin("topicStatus", "-n", "127.0.0.1:9876", "-t", topic);
            try (var recovered = broker.consumer(group, topic)) {
                var record = RocketClient.receive(recovered, 1, Duration.ofSeconds(60)).getFirst();
                assertEquals("disk1", RocketClient.event(record).id());
                assertTrue(
                        Lab.missing(
                                        java.util.Set.of("disk1"),
                                        java.util.List.of(RocketClient.event(record)))
                                .isEmpty());
                recovered.ack(record);
            }
            assertTrue(Lab.risk(new Lab.Durability(true, 1)).contains("单机"));
        }
    }
}
