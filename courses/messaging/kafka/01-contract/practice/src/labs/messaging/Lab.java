package labs.messaging;

import org.apache.kafka.clients.producer.Producer;
import org.apache.kafka.clients.producer.ProducerRecord;
import org.apache.kafka.clients.producer.RecordMetadata;

import java.util.List;
import java.util.concurrent.TimeUnit;

/** 同一订单使用稳定键；顺序只在所选分区内成立。 */
public final class Lab {
    public static List<RecordMetadata> publish(
            Producer<String, String> producer, String topic, List<Event> events) throws Exception {
        // 学习区开始
        java.util.ArrayList<RecordMetadata> result = new java.util.ArrayList<>();
        for (Event event : events) {
            result.add(
                    producer.send(new ProducerRecord<>(topic, event.order(), event.encode()))
                            .get(20, TimeUnit.SECONDS));
        }
        return List.copyOf(result);
        // 学习区结束
    }
}
