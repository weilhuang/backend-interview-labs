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
                            "sh",
                            "-c",
                            "test -d /home/rocketmq/store/commitlog && find"
                                + " /home/rocketmq/store/commitlog -maxdepth 1 -type f -size +0c"
                                + " -print");
            System.err.println("真实CommitLog文件：\n" + files.getStdout() + files.getStderr());
            assertEquals(0, files.getExitCode(), files.getStderr());
            var commitLogs =
                    files.getStdout()
                            .lines()
                            .filter(
                                    path ->
                                            path.matches(
                                                    "/home/rocketmq/store/commitlog/[0-9]{20}"))
                            .toList();
            assertFalse(commitLogs.isEmpty(), "必须观察到真实非空20位CommitLog数据文件：" + files.getStdout());
            broker.getDockerClient()
                    .restartContainerCmd(broker.getContainerId())
                    .withTimeout(5)
                    .exec();
            broker.awaitReady(Duration.ofMinutes(2));
            for (String file : commitLogs) {
                var retained = broker.execInContainer("test", "-s", file);
                assertEquals(0, retained.getExitCode(), "同容器重启必须保留原CommitLog文件：" + file);
            }
            broker.admin("topicStatus", "-n", "127.0.0.1:9876", "-t", topic);
            try (var recovered = broker.consumer(group, topic)) {
                var record = RocketClient.receive(recovered, 1, Duration.ofSeconds(60)).getFirst();
                assertEquals(new Event("disk1", "o1", 1, 100), RocketClient.event(record));
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
