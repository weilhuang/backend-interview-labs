package labs.messaging;

import org.apache.kafka.clients.consumer.Consumer;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.kafka.clients.consumer.OffsetAndMetadata;
import org.apache.kafka.clients.producer.Producer;
import org.apache.kafka.clients.producer.ProducerRecord;
import org.apache.kafka.common.TopicPartition;

import java.util.Map;
import java.util.concurrent.TimeUnit;

public final class Lab {
    public static void transform(
            Producer<String, String> producer,
            Consumer<String, String> consumer,
            ConsumerRecord<String, String> input,
            String output,
            boolean abort)
            throws Exception {
        // 学习区开始
        producer.beginTransaction();
        try {
            producer.send(
                            new ProducerRecord<>(
                                    output,
                                    input.key(),
                                    input.value().toUpperCase(java.util.Locale.ROOT)))
                    .get(15, TimeUnit.SECONDS);
            producer.sendOffsetsToTransaction(
                    Map.of(
                            new TopicPartition(input.topic(), input.partition()),
                            new OffsetAndMetadata(input.offset() + 1)),
                    consumer.groupMetadata());
            if (abort) producer.abortTransaction();
            else producer.commitTransaction();
        } catch (Exception failure) {
            producer.abortTransaction();
            throw failure;
        }
        // 学习区结束
    }
}
