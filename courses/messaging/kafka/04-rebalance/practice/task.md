# C08-04 重平衡、所有权与积压

## 企业场景与学习目标

活动订单积压，准备把库存消费者从一实例扩到两实例。目标是分区真实移交后无旧所有权提交，且能解释热点分区为什么加实例也不解决。

本节范围：先运行完整作者实现，再在 Academy 预览的占位区独立编码，最后对照公开标准解。预计 60–100 分钟；先修不足请回到首页给出的课程。本节真实容器与正反解的已验证提交、环境和证据见课程根目录的验证报告；CLI/CI通过不代替Academy界面与归档验收。

## 概念、机制与图解

本课固定Kafka3.9经典组协议和RangeAssignor，撤销时提交已完成位点，丢失时不能提交。poll耗时预算包含业务处理；达到max.poll.interval可能被踢出组。lag应区分end-position、end-committed和业务处理队列，不能只看一个数字。

```text
第N代:       A拥有 P0,P1
新实例B加入 -> A撤销: 提交完成前缀 -> 清本地状态
第N+1代:     A拥有 P0 | B拥有 P1
失去所有权:  丢弃状态 | 禁止旧一代commit
```

## 一步一步运行、编码与验证

在课程根目录执行，不要在 task 子目录运行。所有数据是随机命名的合成课堂资源。

```bash
./gradlew :kafka-04-rebalance:test
./gradlew :kafka-04-rebalance:test -PwithDocker
./gradlew :kafka-04-rebalance:run
```

1. 运行LabTest检查onPartitionsLost只清理、不提交
2. 运行真实扩容测试：A先完成两分区，再加入B，轮询直到两个assignment各为1
3. 实现撤销时仅提交被撤销分区的已完成位点，finally清理本地状态
4. 改造成慢处理：减少max.poll.interval，观察撤销与恢复，记录poll预算而不依赖固定sleep猜测重平衡完成
5. 独立加一个异步worker，维护每分区连续完成前缀并补乱序完成测试

默认命令只跑无容器用例；带 -PwithDocker 才会启动真实服务。无 Docker 时后者必须失败，不使用 disabledWithoutDocker 自动跳过来制造全绿。第一次依赖下载失败属于环境问题，先检查 Maven Central 与 Wrapper 下载；API 或断言失败再按中文提示检查代码。

## 本节输入与预期结果

P0/P1各三条，A完成后B加入；稳定后A/B各持有一个不同分区，撤销本地位点为空，新所有者end-committed=0。

## 完整调用示例

src/labs/messaging/Usage.java 是可见命令行调用端；无参数打印准确参数说明，有参数连接明确指定的课堂端点。BrokerTest.java 是本节专用业务调用链，展示正常和故障路径；所有测试都在 test/ 中公开。公共 Event、Inbox 与容器夹具在课程根 support/src/labs/messaging/，不依赖作者机器的私有文件。

## 真实源码阅读与断点路线

固定源码：[kafka 3.9.1：clients/src/main/java/org/apache/kafka/clients/consumer/internals/ConsumerCoordinator.java](https://github.com/apache/kafka/blob/f745dfdcee2b9851204ddbbcd423626ab87294bc/clients/src/main/java/org/apache/kafka/clients/consumer/internals/ConsumerCoordinator.java)

固定提交：f745dfdcee2b9851204ddbbcd423626ab87294bc。目标符号：onJoinPrepare。追踪代际切换、revoke/lost回调及提交状态；明确只读所选经典协议路径，不混入ConsumerMembershipManager的新协议。

按入口→关键状态→条件分支→可观察结果阅读；记录一次正常路径和一次失败路径。断点可对官方 sources JAR 附源码调试；本次没有伪造断点截图。support/ 与 Lab 中的自写模型不是上游源码替身。不要从一个模型断言生产系统所有故障都被覆盖。

## 标准答案与逐步解析

回调只在消费者线程使用consumer。撤销在仍具备所有权的阶段尽力提交，异常时清本地状态并让异常上抛，不假装已成功；分区丢失直接清理。测试以assignment和offset证据判定完成，最长45秒失败，不靠睡固定时间后断言。shutdown使用try-with-resources；企业异步版本还需停止接收、等待有界在途和取消。

下方为与工程同源的完整实现及调用方，不隐藏答案。先自己完成再读；已读答案后需换条件盲做才能判断掌握程度。

### Lab.java

```java
package labs.messaging;

import org.apache.kafka.clients.consumer.Consumer;
import org.apache.kafka.clients.consumer.ConsumerRebalanceListener;
import org.apache.kafka.clients.consumer.OffsetAndMetadata;
import org.apache.kafka.common.TopicPartition;

import java.util.Collection;
import java.util.HashMap;
import java.util.Map;

/** 单线程处理示例：只有完成业务的位点能提交，失去所有权后立即丢弃本地状态。 */
public final class Lab implements ConsumerRebalanceListener {
    private final Consumer<String, String> consumer;
    private final Map<TopicPartition, OffsetAndMetadata> completed = new HashMap<>();

    public Lab(Consumer<String, String> consumer) {
        this.consumer = consumer;
    }

    public void completed(TopicPartition partition, long offset) {
        completed.put(partition, new OffsetAndMetadata(offset + 1));
    }

    public Map<TopicPartition, OffsetAndMetadata> pending() {
        return Map.copyOf(completed);
    }

    @Override
    public void onPartitionsRevoked(Collection<TopicPartition> partitions) {
        // 学习区开始
        Map<TopicPartition, OffsetAndMetadata> owned = new HashMap<>();
        for (TopicPartition partition : partitions) {
            if (completed.containsKey(partition)) owned.put(partition, completed.get(partition));
        }
        try {
            if (!owned.isEmpty()) consumer.commitSync(owned);
        } finally {
            partitions.forEach(completed::remove);
        }
        // 学习区结束
    }

    @Override
    public void onPartitionsAssigned(Collection<TopicPartition> partitions) {}

    @Override
    public void onPartitionsLost(Collection<TopicPartition> partitions) {
        // 已经丢失所有权，不能尝试提交旧一代位点。
        partitions.forEach(completed::remove);
    }

    public static long lag(long end, long committed) {
        if (end < 0 || committed < 0 || committed > end)
            throw new IllegalArgumentException("位点范围非法");
        return end - committed;
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
            System.out.println("用法：./gradlew :kafka-04-rebalance:run -PappArgs=127.0.0.1:19092");
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

本地状态O(P)，P为已记录分区数；撤销r个分区需O(r)扫描与一次提交。替代异步worker必须维护每分区连续完成前缀，不能直接提交已完成最大序号。

## 面试问题、标准回答与追问

### 问题1：rebalance一定丢消息吗？

标准回答：不会由这个术语直接推出丢失。正确未提交重放和幂等处理可恢复，提交领先业务则可能丢效果。

追问练习：用本节一个具体测试、状态或故障窗口支撑回答；如果删除前提，构造反例。

### 问题2：为什么onPartitionsLost不能照搬Revoked？

标准回答：Lost意味着已经不拥有这些分区，提交可能陈旧并破坏新所有者恢复位置，应清状态。

追问练习：用本节一个具体测试、状态或故障窗口支撑回答；如果删除前提，构造反例。

### 问题3：lag=0就没有延迟吗？

标准回答：不一定，提交过早、下游异步队列、外部业务失败都会使lag不能代表业务完成。需要端到端事件时间延迟和错误率。

追问练习：用本节一个具体测试、状态或故障窗口支撑回答；如果删除前提，构造反例。

### 问题4：热点key如何处理？

标准回答：同key有序通常把热点固定在一个分区；加消费者无法平摊，需业务拆分、批量、限速或改变顺序约束。

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
