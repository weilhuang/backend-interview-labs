package labs.capstone;

import static org.junit.jupiter.api.Assertions.*;

import org.apache.kafka.clients.admin.Admin;
import org.apache.kafka.clients.consumer.KafkaConsumer;
import org.apache.kafka.common.KafkaException;
import org.apache.kafka.common.config.ConfigException;
import org.junit.jupiter.api.Test;

import java.time.Duration;
import java.util.Map;

/** 构造真实Kafka客户端即可验证配置关系，不需要运行Docker或Kafka broker。 */
class BrokerConfigTest {
    private static final String ABSENT_BROKER = "127.0.0.1:1";

    @Test
    void 旧配置在Admin构造阶段就会因预算倒置失败() {
        KafkaException failure =
                assertThrows(
                        KafkaException.class,
                        () -> {
                            Admin admin =
                                    Admin.create(
                                            Map.of(
                                                    "bootstrap.servers",
                                                    ABSENT_BROKER,
                                                    "default.api.timeout.ms",
                                                    5000));
                            admin.close(Duration.ofMillis(200));
                        });
        Throwable cause = failure;
        while (cause.getCause() != null && !(cause instanceof ConfigException))
            cause = cause.getCause();
        assertInstanceOf(ConfigException.class, cause);
        assertTrue(cause.getMessage().contains("default.api.timeout.ms"));
        assertTrue(cause.getMessage().contains("request.timeout.ms"));
    }

    @Test
    void 应用两种Admin预算都能创建真实客户端并有界关闭() {
        assertTimeoutPreemptively(
                Duration.ofSeconds(5),
                () -> {
                    for (Map<String, Object> configuration :
                            java.util.List.of(
                                    Broker.admin(ABSENT_BROKER),
                                    Broker.healthAdmin(ABSENT_BROKER))) {
                        int request = (Integer) configuration.get("request.timeout.ms");
                        int operation = (Integer) configuration.get("default.api.timeout.ms");
                        assertTrue(request > 0 && request <= operation && operation <= 5000);
                        Admin admin = Admin.create(configuration);
                        admin.close(Duration.ofMillis(200));
                    }
                });
    }

    @Test
    void 消费者现有配置也能创建且不会等待不存在的Broker() {
        assertTimeoutPreemptively(
                Duration.ofSeconds(5),
                () -> {
                    KafkaConsumer<String, String> consumer =
                            new KafkaConsumer<>(Broker.consumer(ABSENT_BROKER, "config-contract"));
                    consumer.close(Duration.ofMillis(200));
                });
    }
}
