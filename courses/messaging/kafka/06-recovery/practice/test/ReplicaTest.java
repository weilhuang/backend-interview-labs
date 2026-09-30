import static org.junit.jupiter.api.Assertions.*;

import labs.messaging.*;

import org.apache.kafka.clients.admin.Admin;
import org.apache.kafka.clients.admin.NewTopic;
import org.apache.kafka.clients.producer.ProducerRecord;
import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import org.testcontainers.containers.Network;
import org.testcontainers.kafka.KafkaContainer;

import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.TimeUnit;

@Tag("docker")
class ReplicaTest {
    @Test
    void 三副本已确认消息在一个节点停止后仍可读写() throws Exception {
        List<KafkaContainer> brokers = new ArrayList<>();
        try (Network network = Network.newNetwork()) {
            try {
                for (int id = 1; id <= 3; id++) {
                    String alias = "broker" + id;
                    brokers.add(
                            KafkaSupport.broker()
                                    .withNetwork(network)
                                    .withNetworkAliases(alias)
                                    .withCreateContainerCmdModifier(
                                            command -> command.withHostName(alias))
                                    .withEnv("CLUSTER_ID", "MkU3OEVBNTcwNTJENDM2Qk")
                                    .withEnv("KAFKA_NODE_ID", Integer.toString(id))
                                    .withEnv(
                                            "KAFKA_CONTROLLER_QUORUM_VOTERS",
                                            "1@broker1:9094,2@broker2:9094,3@broker3:9094")
                                    .withEnv("KAFKA_OFFSETS_TOPIC_REPLICATION_FACTOR", "3")
                                    .withEnv("KAFKA_TRANSACTION_STATE_LOG_REPLICATION_FACTOR", "3")
                                    .withEnv("KAFKA_TRANSACTION_STATE_LOG_MIN_ISR", "2"));
                }
                CompletableFuture.allOf(
                                brokers.stream()
                                        .map(b -> CompletableFuture.runAsync(b::start))
                                        .toArray(CompletableFuture[]::new))
                        .get(4, TimeUnit.MINUTES);
                String bootstrap =
                        String.join(
                                ",",
                                brokers.stream().map(KafkaContainer::getBootstrapServers).toList());
                String topic = "replica-" + java.util.UUID.randomUUID();
                var producerConfig = KafkaSupport.producerProperties(bootstrap);
                producerConfig.put("delivery.timeout.ms", "60000");
                producerConfig.put("request.timeout.ms", "10000");
                producerConfig.put("max.block.ms", "60000");
                try (Admin admin = Admin.create(Map.of("bootstrap.servers", bootstrap));
                        var producer =
                                new org.apache.kafka.clients.producer.KafkaProducer<String, String>(
                                        producerConfig);
                        var consumer = KafkaSupport.consumer(bootstrap, "副本组", "read_committed")) {
                    NewTopic config =
                            new NewTopic(topic, Map.of(0, List.of(1, 2, 3)))
                                    .configs(
                                            Map.of(
                                                    "min.insync.replicas",
                                                    "2",
                                                    "unclean.leader.election.enable",
                                                    "false"));
                    admin.createTopics(List.of(config)).all().get(30, TimeUnit.SECONDS);
                    // CreateTopics成功不代表每个broker已能返回新主题元数据。
                    ReplicaReadiness.awaitTopic(admin, topic, 1, Duration.ofSeconds(45));
                    // 先完成RF=3的组位点主题初始化，隔离初始化和故障恢复两个阶段。
                    consumer.subscribe(List.of(topic));
                    long joinDeadline = System.nanoTime() + Duration.ofSeconds(60).toNanos();
                    while (consumer.assignment().isEmpty() && System.nanoTime() < joinDeadline) {
                        consumer.poll(Duration.ofMillis(200));
                    }
                    assertEquals(1, consumer.assignment().size(), "故障前必须完成真实消费组入组");
                    ReplicaReadiness.awaitTopic(
                            admin, "__consumer_offsets", 0, Duration.ofSeconds(45));
                    producer.send(new ProducerRecord<>(topic, "o1", "停止前已确认"))
                            .get(20, TimeUnit.SECONDS);
                    int leader =
                            admin.describeTopics(List.of(topic))
                                    .allTopicNames()
                                    .get(20, TimeUnit.SECONDS)
                                    .get(topic)
                                    .partitions()
                                    .getFirst()
                                    .leader()
                                    .id();
                    brokers.get(leader - 1).stop();
                    boolean elected = false;
                    String lastObservation = "尚未获得新leader";
                    long electionDeadline = System.nanoTime() + Duration.ofSeconds(75).toNanos();
                    while (!elected && System.nanoTime() < electionDeadline) {
                        try {
                            var recoveredPartition =
                                    admin.describeTopics(List.of(topic))
                                            .allTopicNames()
                                            .get(15, TimeUnit.SECONDS)
                                            .get(topic)
                                            .partitions()
                                            .getFirst();
                            elected =
                                    recoveredPartition.leader() != null
                                            && recoveredPartition.leader().id() != leader
                                            && recoveredPartition.leader().id() >= 1
                                            && recoveredPartition.isr().size() >= 2;
                            lastObservation = recoveredPartition.toString();
                        } catch (java.util.concurrent.ExecutionException
                                | java.util.concurrent.TimeoutException transientFailure) {
                            lastObservation = transientFailure.toString();
                        }
                        if (!elected) Thread.sleep(100);
                    }
                    assertTrue(elected, "等待新leader与至少两个ISR超时：" + lastObservation);
                    producer.send(new ProducerRecord<>(topic, "o2", "故障后已确认"))
                            .get(75, TimeUnit.SECONDS);
                    var records = KafkaSupport.read(consumer, 2, Duration.ofSeconds(45));
                    assertEquals(
                            List.of("停止前已确认", "故障后已确认"),
                            records.stream().map(r -> r.value()).toList());
                }
            } finally {
                for (KafkaContainer broker : brokers) broker.close();
            }
        }
    }
}
