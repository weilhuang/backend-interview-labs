package labs.messaging;

import org.apache.rocketmq.client.apis.consumer.SimpleConsumer;
import org.apache.rocketmq.client.apis.message.MessageView;
import org.apache.rocketmq.client.apis.producer.Producer;

public final class Lab {
    public enum Failure {
        NONE,
        TRANSIENT,
        PERMANENT
    }

    public enum Action {
        ACK,
        RETRY,
        QUARANTINE
    }

    public static Action decide(Failure failure, int attempt, int maxAttempts) {
        // 学习区开始
        if (attempt < 1 || maxAttempts < 1) throw new IllegalArgumentException("尝试次数必须为正数");
        if (failure == Failure.NONE) return Action.ACK;
        if (failure == Failure.PERMANENT || attempt >= maxAttempts) return Action.QUARANTINE;
        return Action.RETRY;
        // 学习区结束
    }

    public static void quarantine(
            Producer producer,
            SimpleConsumer consumer,
            MessageView original,
            String deadLetterTopic)
            throws Exception {
        var buffer = original.getBody().duplicate();
        byte[] body = new byte[buffer.remaining()];
        buffer.get(body);
        producer.send(
                RocketClient.PROVIDER
                        .newMessageBuilder()
                        .setTopic(deadLetterTopic)
                        .setKeys(original.getKeys().toArray(String[]::new))
                        .setTag("invalid")
                        .addProperty("原始主题", original.getTopic())
                        .addProperty("错误类型", "永久业务错误")
                        .setBody(body)
                        .build());
        // 必须确认隔离消息发布成功后才能确认原消息。
        consumer.ack(original);
    }
}
