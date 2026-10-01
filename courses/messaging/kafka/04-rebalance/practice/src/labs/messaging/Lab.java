package labs.messaging;

import org.apache.kafka.clients.consumer.Consumer;
import org.apache.kafka.clients.consumer.ConsumerRebalanceListener;
import org.apache.kafka.clients.consumer.OffsetAndMetadata;
import org.apache.kafka.common.TopicPartition;

import java.util.Collection;
import java.util.HashMap;
import java.util.Map;

/** 单线程处理示例：只有完成业务的位点能提交，失去所有权后立即丢弃本地状态。 */
public final class Lab implements ConsumerRebalanceListener {
    private final Consumer<String, String> consumer;
    private final Map<TopicPartition, OffsetAndMetadata> completed = new HashMap<>();

    public Lab(Consumer<String, String> consumer) {
        this.consumer = consumer;
    }

    public void completed(TopicPartition partition, long offset) {
        completed.put(partition, new OffsetAndMetadata(offset + 1));
    }

    public Map<TopicPartition, OffsetAndMetadata> pending() {
        return Map.copyOf(completed);
    }

    @Override
    public void onPartitionsRevoked(Collection<TopicPartition> partitions) {
        // 学习区开始
        Map<TopicPartition, OffsetAndMetadata> owned = new HashMap<>();
        for (TopicPartition partition : partitions) {
            if (completed.containsKey(partition)) owned.put(partition, completed.get(partition));
        }
        try {
            if (!owned.isEmpty()) consumer.commitSync(owned);
        } finally {
            partitions.forEach(completed::remove);
        }
        // 学习区结束
    }

    @Override
    public void onPartitionsAssigned(Collection<TopicPartition> partitions) {}

    @Override
    public void onPartitionsLost(Collection<TopicPartition> partitions) {
        // 已经丢失所有权，不能尝试提交旧一代位点。
        partitions.forEach(completed::remove);
    }

    public static long lag(long end, long committed) {
        if (end < 0 || committed < 0 || committed > end)
            throw new IllegalArgumentException("位点范围非法");
        return end - committed;
    }
}
