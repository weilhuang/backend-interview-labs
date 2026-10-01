package labs.capstone;

import org.apache.kafka.clients.admin.*;
import org.apache.kafka.common.errors.TopicExistsException;

import java.time.Duration;
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

    /** Admin总API预算必须不小于单次请求预算；不能沿用其默认的30秒请求超时。 */
    public static Map<String, Object> admin(String brokers) {
        return Map.of(
                "bootstrap.servers", brokers,
                "request.timeout.ms", 2000,
                "default.api.timeout.ms", 5000);
    }

    /** 健康探测使用更短的独立预算，不拖住页面刷新。 */
    public static Map<String, Object> healthAdmin(String brokers) {
        return Map.of(
                "bootstrap.servers", brokers,
                "request.timeout.ms", 500,
                "default.api.timeout.ms", 1000);
    }

    public static void initialize(String brokers) throws Exception {
        Admin admin = Admin.create(admin(brokers));
        try {
            try {
                admin.createTopics(List.of(new NewTopic(TOPIC, 3, (short) 1)))
                        .all()
                        .get(6, TimeUnit.SECONDS);
            } catch (java.util.concurrent.ExecutionException e) {
                if (!(e.getCause() instanceof TopicExistsException)) throw e;
            }
        } finally {
            admin.close(Duration.ofSeconds(1));
        }
    }

    public static boolean healthy(String brokers) {
        Admin admin = null;
        try {
            admin = Admin.create(healthAdmin(brokers));
            return !admin.describeCluster().nodes().get(1500, TimeUnit.MILLISECONDS).isEmpty();
        } catch (Exception e) {
            return false;
        } finally {
            if (admin != null) admin.close(Duration.ofMillis(500));
        }
    }
}
