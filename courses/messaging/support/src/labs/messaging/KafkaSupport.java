package labs.messaging;

import org.apache.kafka.clients.admin.Admin;
import org.apache.kafka.clients.admin.NewTopic;
import org.apache.kafka.clients.consumer.ConsumerConfig;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.kafka.clients.consumer.KafkaConsumer;
import org.apache.kafka.clients.producer.KafkaProducer;
import org.apache.kafka.clients.producer.ProducerConfig;
import org.apache.kafka.common.serialization.StringDeserializer;
import org.apache.kafka.common.serialization.StringSerializer;
import org.testcontainers.kafka.KafkaContainer;
import org.testcontainers.utility.DockerImageName;

import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Properties;
import java.util.UUID;
import java.util.concurrent.TimeUnit;

public final class KafkaSupport {
    private KafkaSupport() {}

    public static KafkaContainer broker() {
        return new KafkaContainer(DockerImageName.parse(Images.get("KAFKA_IMAGE")))
                .withEnv("KAFKA_HEAP_OPTS", "-Xms256m -Xmx512m")
                .withCreateContainerCmdModifier(
                        command ->
                                command.getHostConfig()
                                        .withMemory(1073741824L)
                                        .withNanoCPUs(1000000000L))
                .withStartupTimeout(Duration.ofMinutes(3));
    }

    public static Properties producerProperties(String bootstrap) {
        Properties p = new Properties();
        p.put(ProducerConfig.BOOTSTRAP_SERVERS_CONFIG, bootstrap);
        p.put(ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG, StringSerializer.class.getName());
        p.put(ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG, StringSerializer.class.getName());
        p.put(ProducerConfig.ACKS_CONFIG, "all");
        p.put(ProducerConfig.ENABLE_IDEMPOTENCE_CONFIG, "true");
        p.put(ProducerConfig.DELIVERY_TIMEOUT_MS_CONFIG, "15000");
        p.put(ProducerConfig.REQUEST_TIMEOUT_MS_CONFIG, "5000");
        p.put(ProducerConfig.MAX_BLOCK_MS_CONFIG, "15000");
        return p;
    }

    public static KafkaProducer<String, String> producer(String bootstrap) {
        return new KafkaProducer<>(producerProperties(bootstrap));
    }

    public static KafkaConsumer<String, String> consumer(
            String bootstrap, String group, String isolation) {
        Properties p = new Properties();
        p.put(ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG, bootstrap);
        p.put(ConsumerConfig.GROUP_ID_CONFIG, group);
        p.put(ConsumerConfig.KEY_DESERIALIZER_CLASS_CONFIG, StringDeserializer.class.getName());
        p.put(ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG, StringDeserializer.class.getName());
        p.put(ConsumerConfig.ENABLE_AUTO_COMMIT_CONFIG, "false");
        p.put(ConsumerConfig.AUTO_OFFSET_RESET_CONFIG, "earliest");
        p.put(ConsumerConfig.ISOLATION_LEVEL_CONFIG, isolation);
        p.put(ConsumerConfig.MAX_POLL_RECORDS_CONFIG, "20");
        p.put(ConsumerConfig.DEFAULT_API_TIMEOUT_MS_CONFIG, "15000");
        // 本课固定经典组协议，避免把新消费者协议的配置混入本实验。
        p.put(
                ConsumerConfig.PARTITION_ASSIGNMENT_STRATEGY_CONFIG,
                "org.apache.kafka.clients.consumer.RangeAssignor");
        return new KafkaConsumer<>(p);
    }

    public static String topic(String bootstrap, int partitions) throws Exception {
        String name = "lab-" + UUID.randomUUID();
        try (Admin admin = Admin.create(Map.of("bootstrap.servers", bootstrap))) {
            admin.createTopics(List.of(new NewTopic(name, partitions, (short) 1)))
                    .all()
                    .get(20, TimeUnit.SECONDS);
        }
        return name;
    }

    public static List<ConsumerRecord<String, String>> read(
            KafkaConsumer<String, String> consumer, int minimum, Duration timeout) {
        List<ConsumerRecord<String, String>> result = new ArrayList<>();
        long deadline = System.nanoTime() + timeout.toNanos();
        while (result.size() < minimum && System.nanoTime() < deadline) {
            consumer.poll(Duration.ofMillis(200)).forEach(result::add);
        }
        if (result.size() < minimum) {
            throw new AssertionError("等待消息超时，期望至少 " + minimum + "，实际 " + result.size());
        }
        return result;
    }
}
