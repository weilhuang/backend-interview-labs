# C08-03 消费提交与数据库幂等

## 企业场景与学习目标

库存消费事件后更新MySQL，进程在数据库提交成功而offset未提交时退出。目标是重启后重放仍只加一次库存。先修：MySQL事务和唯一约束。

本节范围：先运行完整作者实现，再在 Academy 预览的占位区独立编码，最后对照公开标准解。预计 60–100 分钟；先修不足请回到首页给出的课程。本节真实容器与正反解的已验证提交、环境和证据见课程根目录的验证报告；CLI/CI通过不代替Academy界面与归档验收。

## 概念、机制与图解

自动提交可能领先业务进度。手动提交也无法把外部MySQL事务和Kafka位点变成一个原子提交。采用至少一次交付：先业务事务，后位点；重复窗口由inbox唯一事件ID处理。inbox插入和业务更新必须同事务，先去重再事务外更新仍会丢业务。

```text
poll(offset0) -> [MySQL: inbox(e1)+余额100 COMMIT]
                                      |
                             故障屏障: 此处退出
                                      |
重启poll(offset0) -> 重复键 -> 不再加钱 -> commit(offset1)
```

## 一步一步运行、编码与验证

在课程根目录执行，不要在 task 子目录运行。所有数据是随机命名的合成课堂资源。

```bash
./gradlew :kafka-03-inbox:test
./gradlew :kafka-03-inbox:test -PwithDocker
./gradlew :kafka-03-inbox:run
```

1. 先读可见support/Inbox.java与全部SQL，指出唯一键和事务范围
2. 运行单测理解指定故障屏障；再运行真实Kafka+MySQL测试
3. 按顺序实现Lab.handle，在BEFORE_EFFECT和AFTER_EFFECT_BEFORE_OFFSET两个窗口分别注入失败
4. 最后重启消费者从同一group恢复，断言余额100且committed=1
5. 把commitSync移到业务前，复现实验合同为何失效；恢复标准解再回归

默认命令只跑无容器用例；带 -PwithDocker 才会启动真实服务。无 Docker 时后者必须失败，不使用 disabledWithoutDocker 自动跳过来制造全绿。第一次依赖下载失败属于环境问题，先检查 Maven Central 与 Wrapper 下载；API 或断言失败再按中文提示检查代码。

## 本节输入与预期结果

输入e1/o1/100分：业务前崩溃余额=0，业务提交后崩溃余额=100；重建消费者重放后余额仍100，committed offset=1。

## 完整调用示例

src/labs/messaging/Usage.java 是可见命令行调用端；无参数打印准确参数说明，有参数连接明确指定的课堂端点。BrokerTest.java 是本节专用业务调用链，展示正常和故障路径；所有测试都在 test/ 中公开。公共 Event、Inbox 与容器夹具在课程根 support/src/labs/messaging/，不依赖作者机器的私有文件。

## 真实源码阅读与断点路线

固定源码：[kafka 3.9.1：clients/src/main/java/org/apache/kafka/clients/consumer/internals/ConsumerCoordinator.java](https://github.com/apache/kafka/blob/f745dfdcee2b9851204ddbbcd423626ab87294bc/clients/src/main/java/org/apache/kafka/clients/consumer/internals/ConsumerCoordinator.java)

固定提交：f745dfdcee2b9851204ddbbcd423626ab87294bc。目标符号：commitOffsetsSync。观察generation、分区offset映射、coordinator未知和重试路径；和MySQL事务提交位置画同一时间线。

按入口→关键状态→条件分支→可观察结果阅读；记录一次正常路径和一次失败路径。断点可对官方 sources JAR 附源码调试；本次没有伪造断点截图。support/ 与 Lab 中的自写模型不是上游源码替身。不要从一个模型断言生产系统所有故障都被覆盖。

## 标准答案与逐步解析

事件/订单标识符保留原始大小写与尾空格，MySQL六个身份列显式使用utf8mb4_0900_bin（NO PAD）；不能把自然语言ai_ci比较用在幂等或事务回查身份上。H2只验控制流，真实Case/case/尾空格与错身份回查由MySQL用例证明。

先调用Inbox.apply，其中INSERT inbox和UPDATE balances共享连接与事务。唯一键冲突仅识别MySQL错误1062，其他SQL异常不能当重复吞掉。成功或已处理重复后提交record.offset+1。故障用异常屏障精确停止调用路径，不是声称模拟了OS断电。真实数据库容器保存状态，新的消费者实例证明确实从未提交位点重读。 本例inbox只服务一个业务处理器，多处理器共享表需把消费者身份加入唯一键，避免互相误去重。

下方为与工程同源的完整实现及调用方，不隐藏答案。先自己完成再读；已读答案后需换条件盲做才能判断掌握程度。

### Lab.java

```java
package labs.messaging;

import org.apache.kafka.clients.consumer.Consumer;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.kafka.clients.consumer.OffsetAndMetadata;
import org.apache.kafka.common.TopicPartition;

import java.util.Map;

public final class Lab {
    @FunctionalInterface
    public interface DurableEffect {
        void apply(Event event) throws Exception;
    }

    public static void handle(
            Consumer<String, String> consumer,
            ConsumerRecord<String, String> record,
            Inbox inbox,
            FailurePoint failure)
            throws Exception {
        handle(consumer, record, event -> inbox.apply(event), failure);
    }

    public static void handle(
            Consumer<String, String> consumer,
            ConsumerRecord<String, String> record,
            DurableEffect effect,
            FailurePoint failure)
            throws Exception {
        // 学习区开始
        failure.hit(FailurePoint.BEFORE_EFFECT);
        effect.apply(Event.decode(record.value()));
        failure.hit(FailurePoint.AFTER_EFFECT_BEFORE_OFFSET);
        consumer.commitSync(
                Map.of(
                        new TopicPartition(record.topic(), record.partition()),
                        new OffsetAndMetadata(record.offset() + 1)));
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
            System.out.println("用法：./gradlew :kafka-03-inbox:run -PappArgs=127.0.0.1:19092");
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

持久去重空间随保留事件数增长；唯一索引查找/写入与业务更新产生数据库成本，不是免费O(1)保证。替代是业务表自然唯一键或可证明幂等的条件更新；多处理器共享inbox需(consumer,event_id)复合唯一键。

## 面试问题、标准回答与追问

### 问题1：只在内存Set去重可以吗？

标准回答：只能用于明确标注的进程内模型，重启就失效，且多个实例不共享。这里使用数据库持久唯一约束。

追问练习：用本节一个具体测试、状态或故障窗口支撑回答；如果删除前提，构造反例。

### 问题2：去重记录何时能删除？

标准回答：必须超过可能重放与重复交付的业务窗口并有保留策略。日志仍可重放而去重先清理会再次产生效果。

追问练习：用本节一个具体测试、状态或故障窗口支撑回答；如果删除前提，构造反例。

### 问题3：多个分区可直接提交最高offset吗？

标准回答：必须按分区记录连续已完成前缀。异步处理中offset10完成而9未完成，提交11会跳过9。

追问练习：用本节一个具体测试、状态或故障窗口支撑回答；如果删除前提，构造反例。

### 问题4：这能称为exactly-once吗？

标准回答：只可在业务事务、唯一键、事件ID稳定及保留假设下称业务effect-once。消息仍可能重复，Kafka和MySQL没有此代码提供的全局事务。

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
