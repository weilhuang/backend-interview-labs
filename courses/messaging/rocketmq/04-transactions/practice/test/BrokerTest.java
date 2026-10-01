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
            String rollbackTopic = broker.topic("TRANSACTION");
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
                                .setTopics(topic, rollbackTopic)
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
                    // 回查提交可能重复投递tx1；回滚用独立主题，不能把tx1重复误判成tx2泄露。
                    try (var rollbackConsumer =
                            broker.consumer(broker.group(false), rollbackTopic)) {
                        Event rolledBack = new Event("tx2", "o2", 1, 100);
                        var rollback = recovered.beginTransaction();
                        recovered.send(RocketClient.message(rollbackTopic, rolledBack), rollback);
                        rollback.rollback();
                        long deadline = System.nanoTime() + Duration.ofSeconds(15).toNanos();
                        while (System.nanoTime() < deadline) {
                            var unexpected = rollbackConsumer.receive(10, Duration.ofSeconds(10));
                            assertTrue(
                                    unexpected.isEmpty(),
                                    "独立回滚主题不能下发任何消息，实际事件="
                                            + unexpected.stream()
                                                    .map(RocketClient::event)
                                                    .toList());
                        }
                        // 正向控制：同一消费者必须读到随后提交的事务，排除断连造成的假不可见。
                        Event control = new Event("tx-control", "o-control", 1, 1);
                        Lab.commitLocal(database, control);
                        var committed = recovered.beginTransaction();
                        recovered.send(RocketClient.message(rollbackTopic, control), committed);
                        committed.commit();
                        var visible =
                                RocketClient.receive(rollbackConsumer, 1, Duration.ofSeconds(30));
                        for (var message : visible) {
                            assertEquals(control, RocketClient.event(message), "回滚的tx2始终不可见");
                            rollbackConsumer.ack(message);
                        }
                    }
                }
            }
        }
    }

    @Test
    void 真实MySQL回查不得把其他大小写或尾空格身份认成已提交() throws Exception {
        try (var mysql = new MySQLContainer<>(Images.get("MYSQL_IMAGE"))) {
            mysql.start();
            Inbox database =
                    new Inbox(mysql.getJdbcUrl(), mysql.getUsername(), mysql.getPassword());
            Lab.initialize(database);
            Lab.commitLocal(database, new Event("Case", "o1", 1, 100));
            assertEquals(TransactionResolution.COMMIT, Lab.check(database, "Case"));
            assertEquals(TransactionResolution.UNKNOWN, Lab.check(database, "case"));
            assertEquals(TransactionResolution.UNKNOWN, Lab.check(database, "Case "));
            Lab.commitLocal(database, new Event("case", "o2", 1, 200));
            assertEquals(TransactionResolution.UNKNOWN, Lab.check(database, "case "));
            Lab.commitLocal(database, new Event("case ", "o3", 1, 300));
            for (String id : java.util.List.of("Case", "case", "case ")) {
                assertEquals(TransactionResolution.COMMIT, Lab.check(database, id));
            }
            try (var c = database.connection();
                    var st = c.createStatement();
                    var rows = st.executeQuery("SELECT COUNT(*),SUM(cents) FROM local_orders")) {
                assertTrue(rows.next());
                assertEquals(3, rows.getLong(1));
                assertEquals(600, rows.getLong(2));
            }
        }
    }
}
