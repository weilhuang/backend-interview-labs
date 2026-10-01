package labs.messaging;

import org.apache.rocketmq.client.apis.ClientServiceProvider;
import org.apache.rocketmq.client.apis.consumer.SimpleConsumer;
import org.apache.rocketmq.client.apis.message.Message;
import org.apache.rocketmq.client.apis.message.MessageView;

import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.List;

/** 不依赖Docker的真实gRPC消息构造与接收调用端。 */
public final class RocketClient {
    private RocketClient() {}

    public static final ClientServiceProvider PROVIDER = ClientServiceProvider.loadService();

    public static Message message(String topic, Event event) {
        return PROVIDER.newMessageBuilder()
                .setTopic(topic)
                .setTag("order")
                .setKeys(event.id())
                .setBody(event.encode().getBytes(StandardCharsets.UTF_8))
                .build();
    }

    public static Event event(MessageView view) {
        return Event.decode(StandardCharsets.UTF_8.decode(view.getBody().duplicate()).toString());
    }

    public static List<MessageView> receive(SimpleConsumer consumer, int minimum, Duration timeout)
            throws Exception {
        java.util.ArrayList<MessageView> messages = new java.util.ArrayList<>();
        long deadline = System.nanoTime() + timeout.toNanos();
        while (messages.size() < minimum && System.nanoTime() < deadline) {
            messages.addAll(
                    consumer.receive(
                            Math.max(1, minimum - messages.size()), Duration.ofSeconds(10)));
        }
        if (messages.size() < minimum) throw new AssertionError("等待消息超时，实际收到：" + messages.size());
        return messages;
    }
}
