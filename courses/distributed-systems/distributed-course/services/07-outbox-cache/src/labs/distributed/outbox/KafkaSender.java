package labs.distributed.outbox;

import java.util.Properties;
import java.util.concurrent.TimeUnit;
import org.apache.kafka.clients.producer.*;
import org.apache.kafka.common.serialization.StringSerializer;

public final class KafkaSender implements OutboxStore.Sender, AutoCloseable {
  private final KafkaProducer<String, String> producer;
  private final String topic;

  public KafkaSender(String bootstrap, String topic) {
    this.topic = topic;
    Properties properties = new Properties();
    properties.put(ProducerConfig.BOOTSTRAP_SERVERS_CONFIG, bootstrap);
    properties.put(ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG, StringSerializer.class.getName());
    properties.put(ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG, StringSerializer.class.getName());
    properties.put(ProducerConfig.ACKS_CONFIG, "all");
    properties.put(ProducerConfig.ENABLE_IDEMPOTENCE_CONFIG, "true");
    properties.put(ProducerConfig.MAX_IN_FLIGHT_REQUESTS_PER_CONNECTION, "1");
    properties.put(ProducerConfig.DELIVERY_TIMEOUT_MS_CONFIG, "10000");
    properties.put(ProducerConfig.REQUEST_TIMEOUT_MS_CONFIG, "5000");
    properties.put(ProducerConfig.MAX_BLOCK_MS_CONFIG, "10000");
    producer = new KafkaProducer<>(properties);
  }

  @Override
  public void send(Event event) throws Exception {
    producer
        .send(new ProducerRecord<>(topic, event.sku(), event.encode()))
        .get(12, TimeUnit.SECONDS);
  }

  @Override
  public void close() {
    producer.close(java.time.Duration.ofSeconds(3));
  }
}
