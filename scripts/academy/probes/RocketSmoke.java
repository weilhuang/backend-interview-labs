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
        if (args.length != 7 || !(args[0].equals("write") || args[0].equals("read"))) {
            throw new IllegalArgumentException("需要 write/read、端点、收发主题/组、持久化主题/组、CI 标记");
        }
        if (!"true".equals(System.getenv("CI"))
                || !args[6].matches("totalacademy-ci-\\d+-\\d+")) {
            throw new IllegalArgumentException("只允许独立 CI 项目进行真实消息读写");
        }
        if (args[2].equals(args[4]) || args[3].equals(args[5])) {
            throw new IllegalArgumentException("收发与持久化必须使用不同主题/消费组，不能混淆至少一次重投递语义");
        }
        if (Runtime.version().feature() != 21) throw new IllegalStateException("验收必须使用完整 JDK21");
        var configuration = ClientConfiguration.newBuilder()
                .setEndpoints(args[1]).enableSsl(false).setRequestTimeout(Duration.ofSeconds(10)).build();
        if (args[0].equals("write")) {
            try (var roundtrip = consumer(configuration, args[2], args[3]);
                    var durable = consumer(configuration, args[4], args[5])) {
                // 在空主题建立初始消费位置，避免新消费组默认从最新位置开始。
                initializeEmpty(roundtrip);
                initializeEmpty(durable);
                try (var producer = PROVIDER.newProducerBuilder().setClientConfiguration(configuration)
                        .setTopics(args[2], args[4]).build()) {
                    producer.send(PROVIDER.newMessageBuilder().setTopic(args[2])
                            .setBody((args[6] + "-roundtrip").getBytes(StandardCharsets.UTF_8)).build());
                    receiveAndAck(roundtrip, args[6] + "-roundtrip");
                    // 独立主题只留一条未消费消息。重启读取不得重发，也不要求已 ACK 消息永不重投。
                    producer.send(PROVIDER.newMessageBuilder().setTopic(args[4])
                            .setBody(args[6].getBytes(StandardCharsets.UTF_8)).build());
                }
            }
        } else {
            // 不创建 producer、不发送、不初始化空主题，只读同一个持久化主题中的原消息。
            try (var durable = consumer(configuration, args[4], args[5])) {
                receiveAndAck(durable, args[6]);
            }
        }
        System.out.println("ROCKETMQ_SMOKE_OK=" + args[0]);
    }

    private static SimpleConsumer consumer(ClientConfiguration configuration, String topic, String group) throws Exception {
        return PROVIDER.newSimpleConsumerBuilder().setClientConfiguration(configuration)
                .setConsumerGroup(group).setAwaitDuration(Duration.ofSeconds(5))
                .setSubscriptionExpressions(Map.of(topic, FilterExpression.SUB_ALL)).build();
    }

    private static void initializeEmpty(SimpleConsumer consumer) throws Exception {
        if (!consumer.receive(1, Duration.ofSeconds(15)).isEmpty()) {
            throw new IllegalStateException("新的 CI 主题不应已有消息");
        }
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
