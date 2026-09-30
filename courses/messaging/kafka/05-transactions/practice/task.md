# C08-05 Kafka事务与精确一次边界

## 企业场景与学习目标

读取订单主题，生成标准化主题。输出写成功后输入offset提交失败会重复输出；要求在Kafka范围内原子提交输出记录和输入位点。

本节范围：先运行完整作者实现，再在 Academy 预览的占位区独立编码，最后对照公开标准解。预计 60–100 分钟；先修不足请回到首页给出的课程。本节真实容器与正反解的已验证提交、环境和证据见课程根目录的验证报告；CLI/CI通过不代替Academy界面与归档验收。

## 概念、机制与图解

transactional.id用于事务生产者身份与fencing；initTransactions恢复状态。一次事务包含begin、输出send、sendOffsetsToTransaction与commit。read_committed过滤中止事务；read_uncommitted可看到它们。外部DB和HTTP没有加入这个事务。

```text
输入offset0 -> beginTransaction -> 输出ORDER-1
                         |                 |
                  sendOffsetsToTransaction(offset1)
                         |
              abort: 两者不提交 / commit: 两者一起可见
```

## 一步一步运行、编码与验证

在课程根目录执行，不要在 task 子目录运行。所有数据是随机命名的合成课堂资源。

```bash
./gradlew :kafka-05-transactions:test
./gradlew :kafka-05-transactions:test -PwithDocker
./gradlew :kafka-05-transactions:run
```

1. 读Lab.transform，先运行业务转换小测试
2. 运行真实事务测试：第一次abort，确认输入committed为空；seek回offset0后再次处理并commit
3. 对同输出topic用read_committed/read_uncommitted读取，断言1条与2条
4. 在消费者提交位置改成普通commitSync，解释输出与位点失去原子性并加负例
5. 独立增加另一个相同transactional.id生产者，观察旧实例被fence，异常后关闭而不是无限重试

默认命令只跑无容器用例；带 -PwithDocker 才会启动真实服务。无 Docker 时后者必须失败，不使用 disabledWithoutDocker 自动跳过来制造全绿。第一次依赖下载失败属于环境问题，先检查 Maven Central 与 Wrapper 下载；API 或断言失败再按中文提示检查代码。

## 本节输入与预期结果

输入order-1：第一轮abort后输入提交位点为空；seek并第二轮commit后位点=1，read_committed看到[ORDER-1]，read_uncommitted看到两条ORDER-1。

## 完整调用示例

src/labs/messaging/Usage.java 是可见命令行调用端；无参数打印准确参数说明，有参数连接明确指定的课堂端点。BrokerTest.java 是本节专用业务调用链，展示正常和故障路径；所有测试都在 test/ 中公开。公共 Event、Inbox 与容器夹具在课程根 support/src/labs/messaging/，不依赖作者机器的私有文件。

## 真实源码阅读与断点路线

固定源码：[kafka 3.9.1：clients/src/main/java/org/apache/kafka/clients/producer/internals/TransactionManager.java](https://github.com/apache/kafka/blob/f745dfdcee2b9851204ddbbcd423626ab87294bc/clients/src/main/java/org/apache/kafka/clients/producer/internals/TransactionManager.java)

固定提交：f745dfdcee2b9851204ddbbcd423626ab87294bc。目标符号：sendOffsetsToTransaction。跟踪事务状态机、producer epoch、待发送的AddOffsets/TxnOffsetCommit和EndTxn请求；对照abort与commit分支。

按入口→关键状态→条件分支→可观察结果阅读；记录一次正常路径和一次失败路径。断点可对官方 sources JAR 附源码调试；本次没有伪造断点截图。support/ 与 Lab 中的自写模型不是上游源码替身。不要从一个模型断言生产系统所有故障都被覆盖。

## 标准答案与逐步解析

输出和位点必须由同一producer事务提交，sendOffsetsToTransaction使用正在消费的groupMetadata。abort后消费者本地position并不会自动回退，所以实验显式seek。读隔离过滤事务记录不意味着Kafka删除中止记录。生产者不可共享transactional.id给同时工作的不同分区任务，身份稳定性与并行度需一起设计。

下方为与工程同源的完整实现及调用方，不隐藏答案。先自己完成再读；已读答案后需换条件盲做才能判断掌握程度。

### Lab.java

```java
package labs.messaging;

import org.apache.kafka.clients.consumer.Consumer;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.kafka.clients.consumer.OffsetAndMetadata;
import org.apache.kafka.clients.producer.Producer;
import org.apache.kafka.clients.producer.ProducerRecord;
import org.apache.kafka.common.TopicPartition;

import java.util.Map;
import java.util.concurrent.TimeUnit;

public final class Lab {
    public static void transform(
            Producer<String, String> producer,
            Consumer<String, String> consumer,
            ConsumerRecord<String, String> input,
            String output,
            boolean abort)
            throws Exception {
        // 学习区开始
        producer.beginTransaction();
        try {
            producer.send(
                            new ProducerRecord<>(
                                    output,
                                    input.key(),
                                    input.value().toUpperCase(java.util.Locale.ROOT)))
                    .get(15, TimeUnit.SECONDS);
            producer.sendOffsetsToTransaction(
                    Map.of(
                            new TopicPartition(input.topic(), input.partition()),
                            new OffsetAndMetadata(input.offset() + 1)),
                    consumer.groupMetadata());
            if (abort) producer.abortTransaction();
            else producer.commitTransaction();
        } catch (Exception failure) {
            producer.abortTransaction();
            throw failure;
        }
        // 学习区结束
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
            System.out.println("用法：./gradlew :kafka-05-transactions:run -PappArgs=127.0.0.1:19092");
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

单条变换应用内存O(1)，事务确认与协调有额外RPC开销。批量事务可分摊成本，但变长会拉长可见性与恢复窗口；外部DB效果采用独立inbox/outbox而非扩大EOS口号。

## 面试问题、标准回答与追问

### 问题1：Kafka EOS为什么不能保证扣款一次？

标准回答：外部扣款系统没有加入Kafka事务。消息处理事务成功与HTTP效果存在独立窗口，需外部幂等键或协调协议。

追问练习：用本节一个具体测试、状态或故障窗口支撑回答；如果删除前提，构造反例。

### 问题2：abort后为什么还要seek？

标准回答：事务撤销的是broker事务和提交位点，consumer当前position已经推进；继续poll不会自动回到未处理记录。

追问练习：用本节一个具体测试、状态或故障窗口支撑回答；如果删除前提，构造反例。

### 问题3：read_committed是否等于无阻塞读取？

标准回答：未完成事务可能限制last stable offset，读延迟受事务持续时间影响。长事务会增加可见性等待。

追问练习：用本节一个具体测试、状态或故障窗口支撑回答；如果删除前提，构造反例。

### 问题4：fencing解决什么问题？

标准回答：同事务身份的旧实例被新epoch排除，避免僵尸生产者继续提交；不能替代业务授权或外部数据库锁。

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
