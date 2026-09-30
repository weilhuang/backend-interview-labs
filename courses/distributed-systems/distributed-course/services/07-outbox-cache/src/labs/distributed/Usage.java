package labs.distributed;

import java.time.Duration;
import java.util.*;
import java.util.concurrent.TimeUnit;
import labs.distributed.outbox.*;
import labs.distributed.support.*;
import org.apache.kafka.clients.admin.*;
import org.apache.kafka.clients.consumer.*;
import org.apache.kafka.common.TopicPartition;
import org.apache.kafka.common.serialization.StringDeserializer;
import org.testcontainers.containers.GenericContainer;
import org.testcontainers.kafka.KafkaContainer;
import org.testcontainers.utility.DockerImageName;

public final class Usage {
  public static void main(String[] args) throws Exception {
    if (args.length != 1 || !args[0].equals("--docker")) {
      System.out.println("真实调用：./gradlew :07-outbox-cache:run -PappArgs=--docker");
      System.out.println("将启动隔离MySQL、Kafka、Redis并执行业务写入、发布、消费与缓存；当前未启动容器");
      return;
    }
    try (var mysql = Images.mysql();
        var kafka = new KafkaContainer(DockerImageName.parse(Images.get("KAFKA_IMAGE")));
        var redis =
            new GenericContainer<>(DockerImageName.parse(Images.get("REDIS_IMAGE")))
                .withExposedPorts(6379)) {
      mysql.start();
      kafka.start();
      redis.start();
      var db = Images.database(mysql);
      var outbox = new OutboxStore(db);
      outbox.initialize();
      var projector = new Projector(db);
      projector.initialize();
      String topic = "inventory-demo";
      try (var admin = Admin.create(Map.of("bootstrap.servers", kafka.getBootstrapServers()))) {
        admin
            .createTopics(List.of(new NewTopic(topic, 1, (short) 1)))
            .all()
            .get(20, TimeUnit.SECONDS);
      }
      outbox.change("demo-event", "book", -2);
      try (var sender = new KafkaSender(kafka.getBootstrapServers(), topic)) {
        outbox.publishOne(sender, () -> {});
      }
      Properties settings = new Properties();
      settings.put("bootstrap.servers", kafka.getBootstrapServers());
      settings.put("key.deserializer", StringDeserializer.class.getName());
      settings.put("value.deserializer", StringDeserializer.class.getName());
      settings.put("group.id", "demo-projector");
      settings.put("enable.auto.commit", "false");
      try (var consumer = new KafkaConsumer<String, String>(settings);
          var cache =
              new VersionedCache(
                  redis.getHost(), redis.getMappedPort(6379), Duration.ofSeconds(3))) {
        consumer.assign(List.of(new TopicPartition(topic, 0)));
        consumer.seekToBeginning(consumer.assignment());
        long deadline = System.nanoTime() + Duration.ofSeconds(30).toNanos();
        boolean received = false;
        while (!received && System.nanoTime() < deadline) {
          for (var record : consumer.poll(Duration.ofMillis(200))) {
            var event = Event.decode(record.value());
            projector.apply(event, () -> {});
            cache.invalidate(event);
            cache.fill(event);
            System.out.println("真实读模型缓存：" + cache.get(event.sku()).orElseThrow());
            received = true;
          }
          consumer.commitSync(Duration.ofSeconds(5));
        }
        if (!received) throw new IllegalStateException("消费预算耗尽，检查真实broker日志");
        System.out.println("MySQL投影库存：" + db.scalar("SELECT available FROM read_model"));
      }
    }
  }
}
