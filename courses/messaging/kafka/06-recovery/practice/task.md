# C08-06 副本故障、毒消息与恢复评审

## 企业场景与学习目标

订单已写数据库，发布进程超时重启；消费遇到坏版本；broker节点同时发生滚动维护。需要用outbox、隔离队列、重放和副本证据分别应对。

本节范围：先运行完整作者实现，再在 Academy 预览的占位区独立编码，最后对照公开标准解。预计 60–100 分钟；先修不足请回到首页给出的课程。容器测试目前是可执行待云端 Docker 实证，不代表已经运行成功。

## 概念、机制与图解

outbox把本地业务和待发送事件同事务落库；发布确认后标记之间仍有重复窗口。永久解析失败进入DLQ并保留原文，临时依赖故障采用有界重试。三副本、minISR=2与禁止unclean选主维持已声明故障下的确认边界，不承诺任意多节点断电都不丢。

```text
MySQL事务: 业务行 + outbox(e1)
       -> 发布确认 -> [故障] -> 标sent
             | 重发重复
             v
Kafka -> inbox去重 -> 业务效果
   \-> 坏消息 -> DLQ原文+原因 -> 修复后显式重放
```

## 一步一步运行、编码与验证

在课程根目录执行，不要在 task 子目录运行。所有数据是随机命名的合成课堂资源。

```bash
./gradlew :kafka-06-recovery:test
./gradlew :kafka-06-recovery:test -PwithDocker
./gradlew :kafka-06-recovery:run
```

1. 运行LabTest验证旧schema和坏字段负例
2. 运行BrokerTest，在AFTER_PUBLISH_BEFORE_MARK故障屏障后重发，断言两条消息与一次下游效果
3. 运行ReplicaTest：三个真实broker/controller并发就绪、ISR=3，停止当时leader，断言此前确认消息及故障后发送均可消费
4. 查看deadLetter保留原文和错误原因；独立补DLQ发布失败不得提交原位点的测试
5. 先读下方局限，再设计并实现一版带租约/批次/重试次数的多发布器，重复必须仍被消费端去重

默认命令只跑无容器用例；带 -PwithDocker 才会启动真实服务。无 Docker 时后者必须失败，不使用 disabledWithoutDocker 自动跳过来制造全绿。第一次依赖下载失败属于环境问题，先检查 Maven Central 与 Wrapper 下载；API 或断言失败再按中文提示检查代码。

## 本节输入与预期结果

e1发布确认后、标记前退出：重启发布后真实日志中两条e1；下游balance=100，outbox不再继续重发；DLQ保存“永久格式错误|未知格式”。

## 完整调用示例

src/labs/messaging/Usage.java 是可见命令行调用端；无参数打印准确参数说明，有参数连接明确指定的课堂端点。BrokerTest.java 是本节专用业务调用链，展示正常和故障路径；所有测试都在 test/ 中公开。公共 Event、Inbox 与容器夹具在课程根 support/src/labs/messaging/，不依赖作者机器的私有文件。

## 真实源码阅读与断点路线

固定源码：[kafka 3.9.1：clients/src/main/java/org/apache/kafka/clients/producer/internals/Sender.java](https://github.com/apache/kafka/blob/f745dfdcee2b9851204ddbbcd423626ab87294bc/clients/src/main/java/org/apache/kafka/clients/producer/internals/Sender.java)

固定提交：f745dfdcee2b9851204ddbbcd423626ab87294bc。目标符号：handleProduceResponse。从ProduceResponse错误分类到重试/失败回调追踪，结合ReplicaTest在实际leader退出时观察元数据与重试，不将教学outbox视为Kafka内核。

按入口→关键状态→条件分支→可观察结果阅读；记录一次正常路径和一次失败路径。断点可对官方 sources JAR 附源码调试；本次没有伪造断点截图。support/ 与 Lab 中的自写模型不是上游源码替身。不要从一个模型断言生产系统所有故障都被覆盖。

## 标准答案与逐步解析

先把业务和outbox写同一个事务。示例发布器按ID扫描未发送，确认后标记；它只适合单发布器课堂，不把SELECT无锁当成多实例抢占协议。原始毒消息及原因写入隔离主题，真实测试验证内容。三broker测试用真实ISR条件作为故障屏障，停止leader后证明一个节点损失情形，不能外推多个副本同时失效、机房断电或磁盘损坏。

下方为与工程同源的完整实现及调用方，不隐藏答案。先自己完成再读；已读答案后需换条件盲做才能判断掌握程度。

### Lab.java

```java
package labs.messaging;

import org.apache.kafka.clients.producer.Producer;
import org.apache.kafka.clients.producer.ProducerRecord;

import java.sql.Connection;
import java.util.concurrent.TimeUnit;

/** 数据库 outbox 发布器；确认后标记仍有重复窗口，必须由下游 inbox 去重。 */
public final class Lab {
    public static void enqueue(Inbox database, Event event) throws Exception {
        try (Connection c = database.connection()) {
            c.setAutoCommit(false);
            try (var business = c.prepareStatement("INSERT INTO source_orders VALUES (?, ?)");
                    var outbox =
                            c.prepareStatement(
                                    "INSERT INTO outbox(event_id,payload) VALUES (?,?)")) {
                business.setString(1, event.order());
                business.setLong(2, event.cents());
                business.executeUpdate();
                outbox.setString(1, event.id());
                outbox.setString(2, event.encode());
                outbox.executeUpdate();
                c.commit();
            } catch (Exception failure) {
                c.rollback();
                throw failure;
            }
        }
    }

    public static void publish(
            Inbox database, Producer<String, String> producer, String topic, FailurePoint failure)
            throws Exception {
        // 学习区开始
        try (Connection c = database.connection();
                var select =
                        c.prepareStatement(
                                "SELECT event_id,payload FROM outbox WHERE sent=FALSE ORDER BY"
                                    + " event_id");
                var rows = select.executeQuery()) {
            while (rows.next()) {
                Event event = Event.decode(rows.getString(2));
                producer.send(new ProducerRecord<>(topic, event.order(), event.encode()))
                        .get(15, TimeUnit.SECONDS);
                failure.hit(FailurePoint.AFTER_PUBLISH_BEFORE_MARK);
                try (var mark =
                        c.prepareStatement("UPDATE outbox SET sent=TRUE WHERE event_id=?")) {
                    mark.setString(1, event.id());
                    mark.executeUpdate();
                }
            }
        }
        // 学习区结束
    }

    public static void deadLetter(
            Producer<String, String> producer, String dlq, String original, String error)
            throws Exception {
        producer.send(new ProducerRecord<>(dlq, "解析失败", error + "|" + original))
                .get(15, TimeUnit.SECONDS);
    }
}
```

### Usage.java

```java
package labs.messaging;

/** 独立调用端：传入共享环境端点后发送并读取真实订单事件。 */
public final class Usage {
    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            System.out.println("用法：./gradlew :kafka-06-recovery:run -PappArgs=127.0.0.1:19092");
            System.out.println("无需外部服务的可见检查：./gradlew test；真实服务检查：./gradlew test -PwithDocker");
            return;
        }
        String topic = KafkaSupport.topic(args[0], 1);
        try (var producer = KafkaSupport.producer(args[0]);
                var consumer = KafkaSupport.consumer(args[0], "调用示例-" + topic, "read_committed")) {
            Event event = new Event("演示事件一", "演示订单一", 1, 100);
            producer.send(
                            new org.apache.kafka.clients.producer.ProducerRecord<>(
                                    topic, event.order(), event.encode()))
                    .get();
            consumer.subscribe(java.util.List.of(topic));
            var records = KafkaSupport.read(consumer, 1, java.time.Duration.ofSeconds(30));
            System.out.println("收到真实事件：" + Event.decode(records.getFirst().value()));
        }
    }
}
```

## 成本、复杂度与替代方案

当前WHERE sent=FALSE未设专用索引，扫描成本可能随outbox总行数增长；发送n条为O(n)调用。替代是有索引的分批扫描、租约抢占或CDC，仍需持久幂等和过期治理。

## 面试问题、标准回答与追问

### 问题1：outbox为什么还需要inbox？

标准回答：数据库标记和消息发送不是同一原子操作，确认后标记前退出会重发。下游仍要持久幂等。

追问练习：用本节一个具体测试、状态或故障窗口支撑回答；如果删除前提，构造反例。

### 问题2：DLQ是不是发过去就结束？

标准回答：还要告警、人工或自动修复、授权重放、保留策略和幂等。DLQ也会发布失败，不能先提交原位点。

追问练习：用本节一个具体测试、状态或故障窗口支撑回答；如果删除前提，构造反例。

### 问题3：旧消息多一个字段如何兼容？

标准回答：本课V1严格契约拒绝未知版本并隔离。升级需明确版本解析、默认值、可选字段规则和旧消费者策略，不能静默猜字段。

追问练习：用本节一个具体测试、状态或故障窗口支撑回答；如果删除前提，构造反例。

### 问题4：一个副本宕机成功是否证明零丢失？

标准回答：只证明测试条件：三副本已同步、一个节点停止、剩余多数健康。需要继续验证ISR缩减、网络分区、磁盘/恢复及运维配置才能扩大结论。

追问练习：用本节一个具体测试、状态或故障窗口支撑回答；如果删除前提，构造反例。

## 边界、测试解释与独立迁移

- 可见 LabTest 是快速边界检查；BrokerTest 验证实际broker消息与状态，不能用前者代替后者
- 时间上界只用于判定失败；故障先等待真实消息/位点/锁存器状态，不能靠一次偶然睡眠声称一致性
- 每次真实测试用 try-with-resources 清理自己创建的容器，不重置用户现有数据；不要把课堂明文无认证端点暴露到公网
- 修改一个原假设：重复、乱序、消费者重启、组扩容或数据库不可用，先写失败测试，再解释修复的作用域
- 完成标准：能运行、独立实现、读源码解释分支，并用新反例指出保证不成立的条件

### 提示1
先列出输入、状态和必须保持的不变量，区分消息交付与业务效果。

### 提示2
用本节已有正常测试找最小调用链，再把故障点前后两步写在时间线上。

### 提示3
检查重试是否保留业务标识、确认是否领先持久业务、恢复是否真的重建客户端；然后对照完整标准解。
