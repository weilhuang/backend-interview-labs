package labs.capstone;

import static labs.capstone.Model.*;

import static org.junit.jupiter.api.Assertions.*;

import labs.capstone.protocol.DeliveryGrpc;

import org.junit.jupiter.api.Test;

import java.time.Duration;
import java.util.*;
import java.util.concurrent.TimeUnit;

class DeliveryIntegrationTest {
    @Test
    void 真实Kafka与gRPC覆盖确认丢失重放和乱序取消() throws Exception {
        try (var env = new RealServices()) {
            env.orders.place(new Command("o1", "book", 2), Fault.NONE);
            assertThrows(Unknown.class, () -> env.flow.publish(Fault.AFTER_KAFKA_ACK));
            assertEquals(1, env.db.scalar("SELECT COUNT(*) FROM outbox WHERE published=FALSE"));
            env.flow.publish(Fault.NONE);
            env.rpc.nextFault.set(Fault.AFTER_INBOX_COMMIT);
            assertThrows(
                    io.grpc.StatusRuntimeException.class,
                    () -> env.flow.consume("g1", Duration.ofSeconds(12), Fault.NONE));
            assertEquals(1, env.db.scalar("SELECT COUNT(*) FROM inbox"));
            assertThrows(
                    Unknown.class,
                    () -> env.flow.consume("g1", Duration.ofSeconds(12), Fault.AFTER_RPC_ACK));
            env.flow.consume("g1", Duration.ofSeconds(8), Fault.NONE);
            assertEquals(1, env.db.scalar("SELECT COUNT(*) FROM inbox"));
            assertEquals(1, env.db.scalar("SELECT COUNT(*) FROM deliveries"));
            env.orders.cancel("o1");
            env.flow.publish(Fault.NONE);
            env.flow.consume("g1", Duration.ofSeconds(8), Fault.NONE);
            assertEquals("CANCELLED", env.db.deliveries().getFirst().status());
            assertEquals(2, env.db.scalar("SELECT COUNT(*) FROM inbox"));
            var stub =
                    DeliveryGrpc.newBlockingStub(env.channel)
                            .withDeadlineAfter(2, TimeUnit.SECONDS);
            assertTrue(
                    stub.apply(DeliveryRpc.to(new Event("o1:1", "o1", "book", 2, "RESERVED", 1)))
                            .getDuplicate());
            assertEquals("CANCELLED", env.db.deliveries().getFirst().status());
            assertThrows(
                    io.grpc.StatusRuntimeException.class,
                    () ->
                            stub.apply(
                                    DeliveryRpc.to(
                                            new Event("o1:1", "o1", "book", 3, "RESERVED", 1))));
            // 新身份先到v2，再到尚未写入inbox的v1，确实进入版本防倒退分支。
            env.orders.place(new Command("out-of-order", "book", 1), Fault.NONE);
            env.orders.cancel("out-of-order");
            assertFalse(
                    stub.apply(
                                    DeliveryRpc.to(
                                            new Event(
                                                    "out-of-order:2",
                                                    "out-of-order",
                                                    "book",
                                                    1,
                                                    "CANCELLED",
                                                    2)))
                            .getDuplicate());
            assertFalse(
                    stub.apply(
                                    DeliveryRpc.to(
                                            new Event(
                                                    "out-of-order:1",
                                                    "out-of-order",
                                                    "book",
                                                    1,
                                                    "RESERVED",
                                                    1)))
                            .getDuplicate());
            var reordered =
                    env.db.deliveries().stream()
                            .filter(d -> d.requestId().equals("out-of-order"))
                            .findFirst()
                            .orElseThrow();
            assertEquals(2, reordered.version());
            assertEquals("CANCELLED", reordered.status());
            assertEquals(4, env.db.scalar("SELECT COUNT(*) FROM inbox"));
            // 同一分区已有三个不同事件；第二条失败，不能提交整个poll批次的位置。
            var firstOrder = env.orders.place(new Command("batch-a", "book", 1), Fault.NONE);
            var secondOrder = env.orders.place(new Command("batch-b", "book", 1), Fault.NONE);
            var thirdOrder = env.orders.place(new Command("batch-c", "book", 1), Fault.NONE);
            long firstOffset;
            try (var producer =
                    new org.apache.kafka.clients.producer.KafkaProducer<String, String>(
                            Broker.producer(env.kafka.getBootstrapServers()))) {
                firstOffset =
                        producer.send(
                                        new org.apache.kafka.clients.producer.ProducerRecord<>(
                                                Broker.TOPIC,
                                                0,
                                                firstOrder.requestId(),
                                                Json.write(Event.of(firstOrder))))
                                .get(10, TimeUnit.SECONDS)
                                .offset();
                producer.send(
                                new org.apache.kafka.clients.producer.ProducerRecord<>(
                                        Broker.TOPIC,
                                        0,
                                        secondOrder.requestId(),
                                        Json.write(Event.of(secondOrder))))
                        .get(10, TimeUnit.SECONDS);
                producer.send(
                                new org.apache.kafka.clients.producer.ProducerRecord<>(
                                        Broker.TOPIC,
                                        0,
                                        thirdOrder.requestId(),
                                        Json.write(Event.of(thirdOrder))))
                        .get(10, TimeUnit.SECONDS);
            }
            env.rpc.failBeforeEvent.set("batch-b:1");
            assertThrows(
                    io.grpc.StatusRuntimeException.class,
                    () -> env.flow.consume("batch-boundary", Duration.ofSeconds(12), Fault.NONE));
            try (var admin =
                    org.apache.kafka.clients.admin.Admin.create(
                            Map.of("bootstrap.servers", env.kafka.getBootstrapServers()))) {
                var offsets =
                        admin.listConsumerGroupOffsets("batch-boundary")
                                .partitionsToOffsetAndMetadata()
                                .get(5, TimeUnit.SECONDS);
                assertEquals(
                        firstOffset + 1,
                        offsets.get(new org.apache.kafka.common.TopicPartition(Broker.TOPIC, 0))
                                .offset());
            }
            assertEquals(
                    0,
                    env.db.scalar(
                            "SELECT COUNT(*) FROM inbox WHERE event_id IN"
                                + " ('batch-b:1','batch-c:1')"));
            env.rpc.failBeforeEvent.set(null);
            env.flow.consume("batch-boundary", Duration.ofSeconds(12), Fault.NONE);
            assertEquals(
                    2,
                    env.db.scalar(
                            "SELECT COUNT(*) FROM inbox WHERE event_id IN"
                                + " ('batch-b:1','batch-c:1')"));
            assertTrue(
                    Audit.inspect(env.db.inventory(), env.db.orders(), env.db.deliveries())
                            .isEmpty());
        }
    }
}
