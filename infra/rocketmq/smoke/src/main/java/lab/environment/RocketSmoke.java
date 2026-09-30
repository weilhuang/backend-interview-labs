package lab.environment;

import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.Map;

import org.apache.rocketmq.client.apis.ClientConfiguration;
import org.apache.rocketmq.client.apis.ClientServiceProvider;
import org.apache.rocketmq.client.apis.consumer.FilterExpression;
import org.apache.rocketmq.client.apis.consumer.SimpleConsumer;

/** 只由 guarded CI 项目调用；从真实宿主发布端点验 SDK5 gRPC 与原卷重启后的消息。 */
public final class RocketSmoke {
    private static final ClientServiceProvider PROVIDER = ClientServiceProvider.loadService();
    private RocketSmoke() {}

    public static void main(String[] args) throws Exception {
        if (args.length != 5 || !(args[0].equals("write") || args[0].equals("read"))) {
            throw new IllegalArgumentException("需要 write/read、端点、主题、消费组、CI 标记");
        }
        if (!"true".equals(System.getenv("CI"))
                || !args[4].matches("backend-interview-labs-ci-\\d+-\\d+")) {
            throw new IllegalArgumentException("只允许独立 CI 项目进行真实消息读写");
        }
        if (Runtime.version().feature() != 21) throw new IllegalStateException("验收必须使用完整 JDK21");
        var configuration = ClientConfiguration.newBuilder()
                .setEndpoints(args[1]).enableSsl(false).setRequestTimeout(Duration.ofSeconds(10)).build();
        try (var consumer = PROVIDER.newSimpleConsumerBuilder().setClientConfiguration(configuration)
                .setConsumerGroup(args[3]).setAwaitDuration(Duration.ofSeconds(5))
                .setSubscriptionExpressions(Map.of(args[2], FilterExpression.SUB_ALL)).build()) {
            if (args[0].equals("write")) {
                // 在空主题建立初始消费位置，避免新消费组默认从最新位置开始。
                if (!consumer.receive(1, Duration.ofSeconds(15)).isEmpty()) {
                    throw new IllegalStateException("新的 CI 主题不应已有消息");
                }
                try (var producer = PROVIDER.newProducerBuilder().setClientConfiguration(configuration)
                        .setTopics(args[2]).build()) {
                    producer.send(PROVIDER.newMessageBuilder().setTopic(args[2])
                            .setBody((args[4] + "-roundtrip").getBytes(StandardCharsets.UTF_8)).build());
                    receiveAndAck(consumer, args[4] + "-roundtrip");
                    // 留一条未消费消息，下一次进程在 down/up 后只读取，绝不重新写入。
                    producer.send(PROVIDER.newMessageBuilder().setTopic(args[2])
                            .setBody(args[4].getBytes(StandardCharsets.UTF_8)).build());
                }
            } else {
                receiveAndAck(consumer, args[4]);
            }
        }
        System.out.println("ROCKETMQ_SMOKE_OK=" + args[0]);
    }

    private static void receiveAndAck(SimpleConsumer consumer, String expected) throws Exception {
        long deadline = System.nanoTime() + Duration.ofSeconds(60).toNanos();
        while (System.nanoTime() < deadline) {
            var messages = consumer.receive(1, Duration.ofSeconds(15));
            if (messages.isEmpty()) continue;
            var message = messages.getFirst();
            String actual = StandardCharsets.UTF_8.decode(message.getBody().duplicate()).toString();
            if (!actual.equals(expected)) throw new IllegalStateException("真实消息内容不匹配：" + actual);
            consumer.ack(message);
            return;
        }
        throw new IllegalStateException("60 秒内没有收到预期的持久化消息");
    }
}
