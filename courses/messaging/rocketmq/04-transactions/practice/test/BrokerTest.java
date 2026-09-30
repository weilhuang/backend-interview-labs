import static org.junit.jupiter.api.Assertions.*;

import labs.messaging.*;

import org.apache.rocketmq.client.apis.producer.TransactionResolution;
import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import org.testcontainers.containers.MySQLContainer;

import java.time.Duration;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

@Tag("docker")
class BrokerTest {
    @Test
    void 生产者重启后根据数据库回查提交并且消费幂等() throws Exception {
        try (var broker = new RocketSupport();
                var mysql = new MySQLContainer<>(Images.get("MYSQL_IMAGE"))) {
            broker.start();
            mysql.start();
            Inbox database =
                    new Inbox(mysql.getJdbcUrl(), mysql.getUsername(), mysql.getPassword());
            database.initialize();
            Lab.initialize(database);
            String topic = broker.topic("TRANSACTION");
            Event event = new Event("tx1", "o1", 1, 100);
            try (var consumer = broker.consumer(broker.group(false), topic)) {
                try (var original =
                        RocketClient.PROVIDER
                                .newProducerBuilder()
                                .setClientConfiguration(broker.configuration())
                                .setTopics(topic)
                                .setTransactionChecker(message -> TransactionResolution.UNKNOWN)
                                .build()) {
                    var transaction = original.beginTransaction();
                    original.send(RocketClient.message(topic, event), transaction);
                    assertTrue(consumer.receive(1, Duration.ofSeconds(10)).isEmpty(), "半消息不能提前下发");
                    Lab.commitLocal(database, event);
                    // 确定性窗口：关闭生产者，不调用transaction.commit，让Broker真正发起回查。
                }
                CountDownLatch checked = new CountDownLatch(1);
                try (var recovered =
                        RocketClient.PROVIDER
                                .newProducerBuilder()
                                .setClientConfiguration(broker.configuration())
                                .setTopics(topic)
                                .setTransactionChecker(
                                        message -> {
                                            checked.countDown();
                                            return Lab.check(
                                                    database, RocketClient.event(message).id());
                                        })
                                .build()) {
                    assertTrue(checked.await(90, TimeUnit.SECONDS), "等待服务端回查超时");
                    var delivered =
                            RocketClient.receive(consumer, 1, Duration.ofSeconds(45)).getFirst();
                    assertEquals(event, RocketClient.event(delivered));
                    assertTrue(database.apply(event));
                    assertFalse(database.apply(event), "下游仍然需要自己的持久幂等");
                    assertEquals(100, database.balance("o1"));
                    consumer.ack(delivered);
                    var rollback = recovered.beginTransaction();
                    recovered.send(
                            RocketClient.message(topic, new Event("tx2", "o2", 1, 100)), rollback);
                    rollback.rollback();
                    assertTrue(consumer.receive(1, Duration.ofSeconds(10)).isEmpty(), "回滚消息不能下发");
                }
            }
        }
    }
}
