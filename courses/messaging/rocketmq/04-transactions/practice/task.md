# C09-04 事务消息、本地事务与回查恢复

## 企业场景与学习目标

订单在MySQL提交后生产者退出，事务半消息尚未确认。要求新生产者能根据持久事实回答回查，使该订单消息最终可投递；下游消费重复仍只生效一次。

本节范围：先运行完整作者实现，再在 Academy 预览的占位区独立编码，最后对照公开标准解。预计 60–100 分钟；先修不足请回到首页给出的课程。容器测试目前是可执行待云端 Docker 实证，不代表已经运行成功。

## 概念、机制与图解

半消息首先被broker接受但消费者不可见；本地事务完成后提交或回滚半消息。无法确定时UNKNOWN并等待回查。事务状态必须与本地业务同事务持久化，内存Map在重启后不能作为真相。消息投递和下游数据库不是同一个原子事务。

```text
发送半消息 -> broker暂不可见
     |
MySQL事务: local_orders + local_tx(COMMIT)
     |
[关闭生产者, 未发二次确认]
     |
新生产者 <- broker回查 -> 查local_tx -> COMMIT -> 消费者
                                                |
                                       自己的inbox+业务事务
```

## 一步一步运行、编码与验证

在课程根目录执行，不要在 task 子目录运行。所有数据是随机命名的合成课堂资源。

```bash
./gradlew :rocketmq-04-transactions:test
./gradlew :rocketmq-04-transactions:test -PwithDocker
./gradlew :rocketmq-04-transactions:run
```

1. 运行LabTest，确保不存在/处理中不是ROLLBACK，而是UNKNOWN
2. 运行真实Kafka无关的RocketMQ+MySQL测试，观察半消息不可见
3. 实现commitLocal，把订单写入和COMMIT状态放在同一数据库事务；失败rollback
4. 关闭原生产者但不提交半消息，重建事务生产者，用CountDownLatch证明服务端实际触发checker
5. 回查提交后消费消息，inbox.apply两次仅一次成功；再发ROLLBACK事务验证消费者不可见
6. 独立补数据库回查超时与人工状态修复，不能把查不到和已回滚混成同一个答案

默认命令只跑无容器用例；带 -PwithDocker 才会启动真实服务。无 Docker 时后者必须失败，不使用 disabledWithoutDocker 自动跳过来制造全绿。第一次依赖下载失败属于环境问题，先检查 Maven Central 与 Wrapper 下载；API 或断言失败再按中文提示检查代码。

## 本节输入与预期结果

tx1半消息先不可见；MySQL本地提交、关闭旧生产者后，新checker被服务端真正调用；收到tx1后两次apply仅一次成功，余额100。显式rollback的tx2不可消费。

## 完整调用示例

src/labs/messaging/Usage.java 是可见命令行调用端；无参数打印准确参数说明，有参数连接明确指定的课堂端点。BrokerTest.java 是本节专用业务调用链，展示正常和故障路径；所有测试都在 test/ 中公开。公共 Event、Inbox 与容器夹具在课程根 support/src/labs/messaging/，不依赖作者机器的私有文件。

## 真实源码阅读与断点路线

固定源码：[rocketmq rocketmq-all-5.3.2：broker/src/main/java/org/apache/rocketmq/broker/transaction/queue/TransactionalMessageServiceImpl.java](https://github.com/apache/rocketmq/blob/2baaf044ea9b12a73a89433242b7b7c56a1b89c2/broker/src/main/java/org/apache/rocketmq/broker/transaction/queue/TransactionalMessageServiceImpl.java)

固定提交：2baaf044ea9b12a73a89433242b7b7c56a1b89c2。目标符号：check。跟踪half/op队列、事务超时、检查次数和回查发送，区分COMMIT/ROLLBACK/UNKNOWN。客户端另读固定java-5.0.8的ProducerImpl与TransactionImpl，避免把纯状态枚举当核心源码。

按入口→关键状态→条件分支→可观察结果阅读；记录一次正常路径和一次失败路径。断点可对官方 sources JAR 附源码调试；本次没有伪造断点截图。support/ 与 Lab 中的自写模型不是上游源码替身。不要从一个模型断言生产系统所有故障都被覆盖。

## 标准答案与逐步解析

事务状态表不是随后异步补写的日志，而是本地事务原子组成部分。checker只查询，不重复执行扣款/下单；数据库异常返回UNKNOWN并留给有界重查与运维兜底。原生产者close后重建客户端，真实回查由latch证据判定，最长等待90秒失败。本地提交已发生，不代表下游库存也已提交，后者需独立幂等事务。

下方为与工程同源的完整实现及调用方，不隐藏答案。先自己完成再读；已读答案后需换条件盲做才能判断掌握程度。

### Lab.java

```java
package labs.messaging;

import org.apache.rocketmq.client.apis.producer.TransactionResolution;

import java.sql.Connection;

/** 本地事务状态与订单行同事务持久化；回查从数据库事实恢复。 */
public final class Lab {
    public static void initialize(Inbox database) throws Exception {
        try (Connection c = database.connection();
                var statement = c.createStatement()) {
            statement.execute(
                    "CREATE TABLE local_orders (event_id VARCHAR(100) PRIMARY KEY, cents BIGINT NOT"
                        + " NULL)");
            statement.execute(
                    "CREATE TABLE local_tx (event_id VARCHAR(100) PRIMARY KEY, state VARCHAR(20)"
                        + " NOT NULL)");
        }
    }

    public static void commitLocal(Inbox database, Event event) throws Exception {
        // 学习区开始
        try (Connection c = database.connection()) {
            c.setAutoCommit(false);
            try (var order = c.prepareStatement("INSERT INTO local_orders VALUES (?, ?)");
                    var status = c.prepareStatement("INSERT INTO local_tx VALUES (?, 'COMMIT')")) {
                order.setString(1, event.id());
                order.setLong(2, event.cents());
                order.executeUpdate();
                status.setString(1, event.id());
                status.executeUpdate();
                c.commit();
            } catch (Exception failure) {
                c.rollback();
                throw failure;
            }
        }
        // 学习区结束
    }

    public static TransactionResolution check(Inbox database, String id) {
        try (Connection c = database.connection();
                var query = c.prepareStatement("SELECT state FROM local_tx WHERE event_id=?")) {
            query.setString(1, id);
            try (var row = query.executeQuery()) {
                return row.next() ? resolution(row.getString(1)) : TransactionResolution.UNKNOWN;
            }
        } catch (Exception failure) {
            // 数据库不可用不是业务回滚的证据；让后续回查和人工恢复接管。
            return TransactionResolution.UNKNOWN;
        }
    }

    public static TransactionResolution resolution(String state) {
        return switch (state) {
            case "COMMIT" -> TransactionResolution.COMMIT;
            case "ROLLBACK" -> TransactionResolution.ROLLBACK;
            default -> TransactionResolution.UNKNOWN;
        };
    }
}
```

### Usage.java

```java
package labs.messaging;

/** 可见命令行调用端，连接用户明确指定的课堂Proxy与预建主题。 */
public final class Usage {
    public static void main(String[] args) throws Exception {
        if (args.length != 2) {
            System.out.println("用法：./gradlew :rocketmq-04-transactions:run -PappArgs='127.0.0.1:18081 课堂主题'");
            System.out.println("主题须预先创建为NORMAL类型；真实测试自动创建隔离资源并清理");
            return;
        }
        var config =
                org.apache.rocketmq.client.apis.ClientConfiguration.newBuilder()
                        .setEndpoints(args[0])
                        .enableSsl(false)
                        .build();
        try (var producer =
                RocketClient.PROVIDER
                        .newProducerBuilder()
                        .setClientConfiguration(config)
                        .setTopics(args[1])
                        .build()) {
            var receipt =
                    producer.send(RocketClient.message(args[1], new Event("演示事件", "演示订单", 1, 100)));
            System.out.println("真实消息已确认：" + receipt.getMessageId());
        }
    }
}
```

## 成本、复杂度与替代方案

每次本地提交两次索引写入且事务状态持久占用空间；回查是一次索引查询并有重查开销。替代是outbox轮询或CDC，各自有不同的重复窗口和运维成本。

## 面试问题、标准回答与追问

### 问题1：回查查不到订单就能回滚吗？

标准回答：不总能。事务可能仍在进行、查询读错库或依赖失败；需要持久状态和明确超时/终态协议，不能把未知当失败。

追问练习：用本节一个具体测试、状态或故障窗口支撑回答；如果删除前提，构造反例。

### 问题2：checker能再执行一次本地事务吗？

标准回答：应以事实查询为主。重新执行可能重复业务副作用，并使回查本身变成新的事务流程。需要明确幂等和状态机才可扩展。

追问练习：用本节一个具体测试、状态或故障窗口支撑回答；如果删除前提，构造反例。

### 问题3：事务消息相当于数据库XA吗？

标准回答：不是。它协调本地事务事实与消息可投递性，实现约定条件下最终收敛，并不把下游任意服务纳入同一原子提交。

追问练习：用本节一个具体测试、状态或故障窗口支撑回答；如果删除前提，构造反例。

### 问题4：为什么消费者仍要inbox？

标准回答：broker投递和consumer ack之间有重复窗口，事务消息解决的是生产端关联问题，不能消除消费端副作用重复。

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
