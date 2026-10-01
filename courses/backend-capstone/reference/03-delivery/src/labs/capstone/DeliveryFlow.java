package labs.capstone;

import static labs.capstone.Model.*;

import io.grpc.ManagedChannel;

import labs.capstone.protocol.DeliveryGrpc;

import org.apache.kafka.clients.consumer.*;
import org.apache.kafka.clients.producer.*;
import org.apache.kafka.common.TopicPartition;

import java.sql.*;
import java.time.Duration;
import java.util.*;
import java.util.concurrent.TimeUnit;

/** C14-03：数据库事实到Kafka，再经gRPC写入投影；所有未知窗口都允许重放。 */
public final class DeliveryFlow {
    private final Database db;
    private final String brokers;
    private final ManagedChannel channel;

    public DeliveryFlow(Database db, String brokers, ManagedChannel channel) {
        this.db = db;
        this.brokers = brokers;
        this.channel = channel;
    }

    public int publish(Fault fault) throws Exception {
        int sent = 0;
        long end = System.nanoTime() + Duration.ofSeconds(10).toNanos();
        KafkaProducer<String, String> producer = new KafkaProducer<>(Broker.producer(brokers));
        try (Connection c = db.open()) {
            List<Event> pending = new ArrayList<>();
            try (Statement s = c.createStatement();
                    ResultSet r =
                            s.executeQuery(
                                    "SELECT payload FROM outbox WHERE published=FALSE ORDER BY"
                                        + " sequence_id LIMIT 100")) {
                while (r.next()) pending.add(Json.read(r.getString(1), Event.class));
            }
            for (Event event : pending) {
                long remaining = end - System.nanoTime();
                if (remaining <= 0) break;
                publishOne(
                        () ->
                                producer.send(
                                                new ProducerRecord<>(
                                                        Broker.TOPIC,
                                                        event.requestId(),
                                                        Json.write(event)))
                                        .get(remaining, TimeUnit.NANOSECONDS),
                        () -> {
                            try (PreparedStatement p =
                                    c.prepareStatement(
                                            "UPDATE outbox SET published=TRUE WHERE event_id=?")) {
                                p.setString(1, event.eventId());
                                p.executeUpdate();
                            }
                        },
                        fault);
                sent++;
            }
        } finally {
            producer.close(Duration.ofSeconds(2));
        }
        return sent;
    }

    public int consume(String group, Duration budget, Fault fault) throws Exception {
        int count = 0;
        long end = System.nanoTime() + budget.toNanos();
        KafkaConsumer<String, String> consumer =
                new KafkaConsumer<>(Broker.consumer(brokers, group));
        try {
            consumer.subscribe(List.of(Broker.TOPIC));
            pollLoop:
            while (System.nanoTime() < end) {
                ConsumerRecords<String, String> records = consumer.poll(Duration.ofMillis(200));
                for (ConsumerRecord<String, String> record : records) {
                    long remaining = end - System.nanoTime();
                    if (remaining <= 0) break pollLoop;
                    Event event = Json.read(record.value(), Event.class);
                    consumeOne(
                            () ->
                                    DeliveryGrpc.newBlockingStub(channel)
                                            .withDeadlineAfter(
                                                    Math.min(
                                                            remaining,
                                                            Duration.ofSeconds(2).toNanos()),
                                                    TimeUnit.NANOSECONDS)
                                            .apply(DeliveryRpc.to(event)),
                            () ->
                                    consumer.commitSync(
                                            Map.of(
                                                    new TopicPartition(
                                                            record.topic(), record.partition()),
                                                    new OffsetAndMetadata(record.offset() + 1)),
                                            Duration.ofSeconds(2)),
                            fault);
                    count++;
                }
            }
        } finally {
            consumer.close(Duration.ofSeconds(2));
        }
        return count;
    }

    @FunctionalInterface
    public interface Checked {
        void run() throws Exception;
    }

    public static void publishOne(Checked send, Checked mark, Fault fault) throws Exception {
        // 学习区开始
        send.run();
        if (fault == Fault.AFTER_KAFKA_ACK) throw new Unknown("Kafka已确认但outbox未标记，下一轮会重复发布");
        mark.run();
        // 学习区结束
    }

    public static void consumeOne(Checked rpc, Checked commit, Fault fault) throws Exception {
        // 学习区开始
        rpc.run();
        if (fault == Fault.AFTER_RPC_ACK) throw new Unknown("RPC已确认但Kafka位点未提交，下一轮会再次调用");
        commit.run();
        // 学习区结束
    }
}
