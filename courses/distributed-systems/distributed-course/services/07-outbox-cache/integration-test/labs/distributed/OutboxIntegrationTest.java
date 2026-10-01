package labs.distributed;

import static org.junit.jupiter.api.Assertions.*;

import java.time.Duration;
import java.util.*;
import java.util.concurrent.TimeUnit;
import labs.distributed.outbox.*;
import labs.distributed.support.*;
import org.apache.kafka.clients.admin.*;
import org.apache.kafka.clients.consumer.*;
import org.apache.kafka.common.TopicPartition;
import org.apache.kafka.common.serialization.StringDeserializer;
import org.junit.jupiter.api.Test;
import org.testcontainers.containers.GenericContainer;
import org.testcontainers.kafka.KafkaContainer;
import org.testcontainers.utility.DockerImageName;

class OutboxIntegrationTest {
  @Test
  void 发布后标记前崩溃产生重复但读模型收敛并拒绝旧缓存回填() throws Exception {
    try (var mysql = Images.mysql();
        var kafka = new KafkaContainer(DockerImageName.parse(Images.get("KAFKA_IMAGE")));
        var redis =
            new GenericContainer<>(DockerImageName.parse(Images.get("REDIS_IMAGE")))
                .withExposedPorts(6379)) {
      mysql.start();
      kafka.start();
      redis.start();
      var db = Images.database(mysql);
      var store = new OutboxStore(db);
      store.initialize();
      var projector = new Projector(db);
      projector.initialize();
      try (var admin = Admin.create(Map.of("bootstrap.servers", kafka.getBootstrapServers()))) {
        admin
            .createTopics(List.of(new NewTopic("inventory-events", 1, (short) 1)))
            .all()
            .get(20, TimeUnit.SECONDS);
      }
      var event = store.change("e1", "book", -3);
      try (var sender = new KafkaSender(kafka.getBootstrapServers(), "inventory-events")) {
        assertThrows(
            IllegalStateException.class,
            () ->
                store.publishOne(
                    sender,
                    () -> {
                      throw new IllegalStateException("消息已确认但发布标记未提交");
                    }));
        assertEquals(0, db.scalar("SELECT published FROM outbox"));
      }
      // 新生产者身份重放，Kafka传输级幂等不能消除新的业务发送。
      try (var recoveredSender = new KafkaSender(kafka.getBootstrapServers(), "inventory-events")) {
        assertTrue(new OutboxStore(db).publishOne(recoveredSender, () -> {}));
      }
      Properties properties = new Properties();
      properties.put("bootstrap.servers", kafka.getBootstrapServers());
      properties.put("key.deserializer", StringDeserializer.class.getName());
      properties.put("value.deserializer", StringDeserializer.class.getName());
      properties.put("group.id", "outbox-test");
      properties.put("enable.auto.commit", "false");
      properties.put("auto.offset.reset", "earliest");
      int messages = 0;
      int applied = 0;
      try (var consumer = new KafkaConsumer<String, String>(properties);
          var cache =
              new VersionedCache(
                  redis.getHost(), redis.getMappedPort(6379), Duration.ofMillis(300))) {
        consumer.assign(List.of(new TopicPartition("inventory-events", 0)));
        consumer.seekToBeginning(consumer.assignment());
        long end = System.nanoTime() + Duration.ofSeconds(30).toNanos();
        while (messages < 2 && System.nanoTime() < end) {
          for (var record : consumer.poll(Duration.ofMillis(200))) {
            Event received = Event.decode(record.value());
            if (projector.apply(received, () -> {})) applied++;
            // 即使是重复事件也再次失效；崩溃可能发生于数据库提交后、Redis更新前。
            cache.invalidate(received);
            messages++;
          }
          consumer.commitSync(Duration.ofSeconds(5));
        }
        assertEquals(2, messages);
        assertEquals(1, applied);
        assertEquals(7, db.scalar("SELECT available FROM read_model"));
        assertTrue(cache.fill(event));
        var newer = store.change("e2", "book", -1);
        projector.apply(newer, () -> {});
        cache.invalidate(newer);
        assertFalse(cache.fill(event));
        assertTrue(cache.get("book").isEmpty());
        assertTrue(cache.fill(newer));
        assertEquals(6, cache.get("book").orElseThrow().available());
        long expires = System.nanoTime() + Duration.ofSeconds(3).toNanos();
        while (cache.get("book").isPresent() && System.nanoTime() < expires) Thread.sleep(20);
        assertTrue(cache.get("book").isEmpty());
      }
    }
  }
}
