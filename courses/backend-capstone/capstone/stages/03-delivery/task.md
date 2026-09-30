# 03 Kafka、gRPC与每个确认窗口的重放

## 本节要交付什么

异步链路包含三种不同事实：订单数据库已经提交；Kafka已确认消息；接收端inbox和配送读模型已经提交。任何一条网络应答都可能丢失。Kafka生产者幂等只处理生产者会话内的重试，重新创建生产者再次发布同一业务事件仍可重复。

本节实现publishOne与consumeOne，要求先完成业务效果再推进确认。生产者收到Kafka确认后才更新outbox.published。消费者等待gRPC成功后，提交该分区record.offset()+1。接收端先写inbox唯一事件号，再更新读模型，二者同事务。相同事件号不同载荷拒绝；版本2的取消到达后，版本1的预留不得回退读模型。

Checked回调是为了对“效果/确认顺序”做可控单元测试，真实调用方仍是KafkaProducer、KafkaConsumer和生成的gRPC stub。真实传输、MySQL唯一键、超时后重放由integrationTest单独证明。完成后保留一张故障窗口表，不能把单元替身的通过写成真实MQ证明。

## 先运行完整调用方

执行place→publish→consume，检查outbox变已发布、inbox一条、读模型RESERVED。打开AFTER_KAFKA_ACK后第一次发布抛Unknown，但Kafka已经有记录；再次publish和consume最终仍只有一条inbox。再在接收端提交后丢失RPC应答、在RPC确认后丢失Kafka提交，各重放一次。

从课程根运行 `./gradlew :03-delivery:test :03-delivery:usage`。实际数据库与网络验收用 `./gradlew :03-delivery:integrationTest`，需要Docker。完整网页调用用 `CAPSTONE_STAGE=03-delivery scripts/course.sh start`。所有测试和调用方都可见；不需要先抄完其他阶段的学习区。

```text
订单事务     outbox       Kafka日志       gRPC接收事务       消费位点
  commit ------>| --send--->| --poll---> [inbox + 读模型] ----> commit(n+1)
                |   A应答丢失      B超时未知      C应答丢失
                +--可重复发布------+--可重复调用----+
                       唯一事件号 + 载荷一致 + 单调版本
```

## 完整项目在哪里

本节只替换 `src/labs/capstone/DeliveryFlow.java`。公共应用在 `app/src/main/java/labs/capstone/`，中文页面在 `app/src/main/resources/static/index.html`，其他已完成依赖在公开 `reference/src/labs/capstone/`。Gradle显式排除本节对应的reference同名类，防止测试绕过你的实现。`test/`与`integration-test/`是本节测试；`shared/`是可见的公共测试支撑。根README给出完整结构、接口与启动依赖。

## 逐步动手

1. 在纸上写出本节的失败分支，先预测每次调用是否允许推进状态
2. 运行现有测试，逐个实现学习区；为一个边界补充可见测试
3. 用Usage或页面实际调用，再运行真实集成；记录编译、快测、容器、浏览器各自结果
4. 不看下方答案，解释一个错误实现为什么会被你的新测试拒绝

## 递进提示

1. 把send/mark和rpc/commit分别当作有顺序的两个操作；前一个失败时后一个绝不能执行。
2. 故障注入必须放在效果成功之后、确认之前，才能真正暴露未知窗口。
3. Kafka位点是下一条要处理的位置。不要批量提交尚未完成的记录，也不要启用自动提交。

## 核心源码与断点证据

在[Kafka3.9.1 KafkaConsumer.commitSync](https://github.com/apache/kafka/blob/3.9.1/clients/src/main/java/org/apache/kafka/clients/consumer/KafkaConsumer.java)与[gRPC1.71.0 ClientCalls.blockingUnaryCall](https://github.com/grpc/grpc-java/blob/v1.71.0/stub/src/main/java/io/grpc/stub/ClientCalls.java)定位确认与异常边界。阅读[gRPC deadline说明](https://grpc.io/docs/guides/deadlines/)。断点分别放在DeliveryStore.commit、RPC返回和consumer.commitSync，故意让前一位置完成而后一位置失败，记录数据库行数与消费组位点。此实验是一个broker，不覆盖副本选主。

## 面试递进

**机制：inbox为何必须与业务写入同事务？**

先记录inbox后业务失败会永久丢失效果；先业务后去重失败会重复执行。

**边界：gRPC DEADLINE_EXCEEDED能直接补偿库存吗？**

不能，服务端可能已经提交。先按事件号重放或查询，不能把未知结果判定为失败。

**取舍：为什么不做跨MySQL与Kafka的XA？**

outbox把原子性缩在本地数据库，接受重复和短暂延迟，换取可恢复的异步边界；不是消除了复杂性。

**追问：遇到永久非法消息会怎样？**

本轮消费中止、失败位点不提交，其他分区也可能暂时受阻；保留证据供人工修复或审核后隔离。生产化需要有审计的隔离队列策略，不能悄悄跳过。

## 标准答案与解释（直接可读）

下面是完整作者实现，不依赖折叠渲染或解锁。先对照关键分支，再重新独立实现；公开答案不会被导出排除。

```java
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
```

为什么这样实现：前面定义的业务状态、失败边界与源码分支必须对应到代码；每次确认都只能声明它前面的效果已经完成。测试既检查返回值，也检查持久化事实和不会发生的副作用。模仿代码排版不是目标，能用不同写法维持相同合同才算通过。
