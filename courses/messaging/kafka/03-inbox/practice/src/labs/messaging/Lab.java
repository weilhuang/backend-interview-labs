package labs.messaging;

import org.apache.kafka.clients.consumer.Consumer;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.kafka.clients.consumer.OffsetAndMetadata;
import org.apache.kafka.common.TopicPartition;

import java.util.Map;

public final class Lab {
    @FunctionalInterface
    public interface DurableEffect {
        void apply(Event event) throws Exception;
    }

    public static void handle(
            Consumer<String, String> consumer,
            ConsumerRecord<String, String> record,
            Inbox inbox,
            FailurePoint failure)
            throws Exception {
        handle(consumer, record, event -> inbox.apply(event), failure);
    }

    public static void handle(
            Consumer<String, String> consumer,
            ConsumerRecord<String, String> record,
            DurableEffect effect,
            FailurePoint failure)
            throws Exception {
        // 学习区开始
        failure.hit(FailurePoint.BEFORE_EFFECT);
        effect.apply(Event.decode(record.value()));
        failure.hit(FailurePoint.AFTER_EFFECT_BEFORE_OFFSET);
        consumer.commitSync(
                Map.of(
                        new TopicPartition(record.topic(), record.partition()),
                        new OffsetAndMetadata(record.offset() + 1)));
        // 学习区结束
    }
}
