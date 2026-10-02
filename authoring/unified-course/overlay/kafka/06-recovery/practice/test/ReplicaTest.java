import static org.junit.jupiter.api.Assertions.*;

import labs.messaging.*;

import org.apache.kafka.clients.admin.Admin;
import org.apache.kafka.clients.admin.NewTopic;
import org.apache.kafka.clients.admin.DescribeClusterOptions;
import org.apache.kafka.common.Uuid;
import org.apache.kafka.clients.producer.ProducerRecord;
import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import org.testcontainers.containers.Network;
import org.testcontainers.kafka.KafkaContainer;

import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.TimeUnit;

@Tag("docker")
class ReplicaTest {
    @Test
    void 三副本已确认消息在一个节点停止后仍可读写() throws Exception {
        List<KafkaContainer> brokers = new ArrayList<>();
        ReplicaEvidence evidence = new ReplicaEvidence();
        ReplicaRecovery.Evidence recovery = new ReplicaRecovery.Evidence();
        try (Network network = Network.newNetwork()) {
            try {
                for (int id = 1; id <= 3; id++) {
                    String alias = "broker" + id;
                    int brokerId = id;
                    brokers.add(
                            KafkaSupport.broker()
                                    .withLogConsumer(frame -> evidence.container(brokerId, frame))
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
                Admin admin = Admin.create(Map.of(
                        "bootstrap.servers", bootstrap, "client.id", "replica-initial-admin"));
                try (var producer =
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
                    // 注入前最后一个快照仍须证明RF3/ISR3，而非只读leader。
                    var before = ReplicaReadiness.awaitTopic(admin, topic, 1, Duration.ofSeconds(45));
                    int leader = before.partitions().getFirst().leader().id();
                    assertTrue(Set.of(1, 2, 3).contains(leader), "leader必须属于本夹具");
                    assertNotEquals(Uuid.ZERO_UUID, before.topicId(), "必须取得真实topic UUID");
                    var cluster = admin.describeCluster(new DescribeClusterOptions().timeoutMs(5000));
                    var nodes = cluster.nodes().get(5, TimeUnit.SECONDS);
                    var controller = cluster.controller().get(5, TimeUnit.SECONDS);
                    evidence.stage("before-stop", "nodes=" + nodes.stream().map(n -> n.id()).toList()
                            + ", controller=" + (controller == null ? -1 : controller.id())
                            + ", " + ReplicaRecovery.partitionEvidence(before));
                    Set<Integer> survivors = new java.util.HashSet<>(Set.of(1, 2, 3));
                    survivors.remove(leader);
                    // 必须在stop/remove之前保存端点。未停止不等于健康，后续仍须真实响应。
                    String recoveryBootstrap = String.join(
                            ",", survivors.stream().sorted()
                                    .map(id -> brokers.get(id - 1).getBootstrapServers()).toList());
                    evidence.stage("stop-leader", "stoppedId=" + leader + ", survivors=" + survivors
                            + ", observerBootstrap=" + recoveryBootstrap);
                    brokers.get(leader - 1).stop();
                    ReplicaRecovery.await(recoveryBootstrap, before.topicId(), leader, survivors,
                            Duration.ofSeconds(75), recovery);
                    evidence.stage("observer-closed", recovery.toString());
                    producer.send(new ProducerRecord<>(topic, "o2", "故障后已确认"))
                            .get(75, TimeUnit.SECONDS);
                    var records = KafkaSupport.read(consumer, 2, Duration.ofSeconds(45));
                    assertEquals(
                            List.of("停止前已确认", "故障后已确认"),
                            records.stream().map(r -> r.value()).toList());
                    evidence.stage("read-write-confirmed", "records=2");
                } finally {
                    // setup Admin不是恢复observer；禁止其默认close无限拖长失败清理。
                    admin.close(Duration.ofMillis(1));
                }
            } catch (Exception | AssertionError failure) {
                // 仅输出已缓存在内存的白名单证据，不在deadline后请求inspect/logs/quorum。
                failure.addSuppressed(new AssertionError(
                        "ReplicaTest evidence: " + recovery + "\n" + evidence.snapshot()));
                throw failure;
            } finally {
                for (KafkaContainer broker : brokers) broker.close();
            }
        }
    }
}
