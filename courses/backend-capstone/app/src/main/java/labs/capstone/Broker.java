package labs.capstone;

import org.apache.kafka.clients.admin.*;
import org.apache.kafka.common.errors.TopicExistsException;

import java.util.*;
import java.util.concurrent.TimeUnit;

public final class Broker {
    public static final String TOPIC = "capstone-orders-v1";

    private Broker() {}

    public static Map<String, Object> producer(String brokers) {
        Map<String, Object> p = new HashMap<>();
        p.put("bootstrap.servers", brokers);
        p.put("key.serializer", "org.apache.kafka.common.serialization.StringSerializer");
        p.put("value.serializer", "org.apache.kafka.common.serialization.StringSerializer");
        p.put("acks", "all");
        p.put("enable.idempotence", true);
        p.put("delivery.timeout.ms", 10000);
        p.put("request.timeout.ms", 3000);
        p.put("max.block.ms", 5000);
        return p;
    }

    public static Map<String, Object> consumer(String brokers, String group) {
        Map<String, Object> p = new HashMap<>();
        p.put("bootstrap.servers", brokers);
        p.put("group.id", group);
        p.put("key.deserializer", "org.apache.kafka.common.serialization.StringDeserializer");
        p.put("value.deserializer", "org.apache.kafka.common.serialization.StringDeserializer");
        p.put("enable.auto.commit", false);
        p.put("auto.offset.reset", "earliest");
        p.put("max.poll.records", 50);
        p.put("default.api.timeout.ms", 5000);
        return p;
    }

    public static void initialize(String brokers) throws Exception {
        try (Admin admin =
                Admin.create(
                        Map.of("bootstrap.servers", brokers, "default.api.timeout.ms", 5000))) {
            try {
                admin.createTopics(List.of(new NewTopic(TOPIC, 3, (short) 1)))
                        .all()
                        .get(10, TimeUnit.SECONDS);
            } catch (java.util.concurrent.ExecutionException e) {
                if (!(e.getCause() instanceof TopicExistsException)) throw e;
            }
        }
    }

    public static boolean healthy(String brokers) {
        try (Admin admin =
                Admin.create(
                        Map.of(
                                "bootstrap.servers",
                                brokers,
                                "default.api.timeout.ms",
                                1000,
                                "request.timeout.ms",
                                1000))) {
            return !admin.describeCluster().nodes().get(1500, TimeUnit.MILLISECONDS).isEmpty();
        } catch (Exception e) {
            return false;
        }
    }
}
