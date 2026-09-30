package labs.messaging;

import org.apache.kafka.clients.producer.ProducerConfig;

import java.util.Properties;

/** 确认、幂等和有界等待必须一起配置。 */
public final class Lab {
    public static Properties reliable(String bootstrap) {
        // 学习区开始
        Properties config = KafkaSupport.producerProperties(bootstrap);
        config.put(ProducerConfig.ACKS_CONFIG, "all");
        config.put(ProducerConfig.ENABLE_IDEMPOTENCE_CONFIG, "true");
        config.put(ProducerConfig.MAX_IN_FLIGHT_REQUESTS_PER_CONNECTION, "5");
        return config;
        // 学习区结束
    }
}
