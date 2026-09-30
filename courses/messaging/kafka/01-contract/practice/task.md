# C08-01 日志分区与消费契约

## 企业场景与学习目标

订单服务每次状态变更写事件，库存和审计分别消费。目标是同一订单的三次变更按顺序到达，同时审计组不会抢走库存组的消息。先修：Java集合、资源关闭、C04调用链。

本节范围：先运行完整作者实现，再在 Academy 预览的占位区独立编码，最后对照公开标准解。预计 60–100 分钟；先修不足请回到首页给出的课程。本节真实容器与正反解的已验证提交、环境和证据见课程根目录的验证报告；CLI/CI通过不代替Academy界面与归档验收。

## 概念、机制与图解

topic 是逻辑事件流，partition 是追加日志与并行度边界。offset 是分区内位置，不是全局消息编号。key 决定默认分区；相同 key 在分区数不变时路由一致。扩分区会改变键映射，旧新分区间不保证顺序。consumer group 对每个分区分配所有者；两个独立组各自有位点。

```text
订单o1 --key=o1--> 分区P0: [e1, e2, e3]
订单o2 --key=o2--> 分区P1: [e4, e5]
                       |              |
库存组:              消费者A        消费者B
审计组:              消费者C        消费者C
```

## 一步一步运行、编码与验证

在课程根目录执行，不要在 task 子目录运行。所有数据是随机命名的合成课堂资源。

```bash
./gradlew :kafka-01-contract:test
./gradlew :kafka-01-contract:test -PwithDocker
./gradlew :kafka-01-contract:run
```

1. 运行本节 LabTest，确认事件编码往返以及坏版本被拒绝
2. 运行 BrokerTest，观察三个相同 key 的 RecordMetadata.partition 一致，消费序号为1/2/3
3. 只修改 Lab.publish：逐个按订单键发送并等待确认，禁止把所有订单随机分区
4. 增加第二订单和第二消费组，验证每组都拿到自己的完整事件，再给 topic 扩容并记录键映射变化

默认命令只跑无容器用例；带 -PwithDocker 才会启动真实服务。无 Docker 时后者必须失败，不使用 disabledWithoutDocker 自动跳过来制造全绿。第一次依赖下载失败属于环境问题，先检查 Maven Central 与 Wrapper 下载；API 或断言失败再按中文提示检查代码。

## 本节输入与预期结果

输入o1的e1/e2/e3，sequence=1/2/3；三个发送结果partition相同，消费值序号为[1,2,3]，单分区offset为[0,1,2]。

## 完整调用示例

src/labs/messaging/Usage.java 是可见命令行调用端；无参数打印准确参数说明，有参数连接明确指定的课堂端点。BrokerTest.java 是本节专用业务调用链，展示正常和故障路径；所有测试都在 test/ 中公开。公共 Event、Inbox 与容器夹具在课程根 support/src/labs/messaging/，不依赖作者机器的私有文件。

## 真实源码阅读与断点路线

固定源码：[kafka 3.9.1：clients/src/main/java/org/apache/kafka/clients/producer/internals/BuiltInPartitioner.java](https://github.com/apache/kafka/blob/f745dfdcee2b9851204ddbbcd423626ab87294bc/clients/src/main/java/org/apache/kafka/clients/producer/internals/BuiltInPartitioner.java)

固定提交：f745dfdcee2b9851204ddbbcd423626ab87294bc。目标符号：partitionForKey。检查 keyBytes、murmur2 和 numPartitions，手算同key扩容前后映射；这是默认键路由分支，不代表自定义Partitioner。

按入口→关键状态→条件分支→可观察结果阅读；记录一次正常路径和一次失败路径。断点可对官方 sources JAR 附源码调试；本次没有伪造断点截图。support/ 与 Lab 中的自写模型不是上游源码替身。不要从一个模型断言生产系统所有故障都被覆盖。

## 标准答案与逐步解析

生产者按业务订单号选择 key，序列号放在消息体里用来检查顺序。同步等待 send 的 Future，使课堂先得到清晰的发送顺序；企业吞吐场景可批量异步，但仍须处理回调、错误和关闭。测试既比较分区，又比较序号，不能用收到三条代替顺序正确。时间开销约为三次往返；替代设计是按分区有序流水发送。

下方为与工程同源的完整实现及调用方，不隐藏答案。先自己完成再读；已读答案后需换条件盲做才能判断掌握程度。

### Lab.java

```java
package labs.messaging;

import org.apache.kafka.clients.producer.Producer;
import org.apache.kafka.clients.producer.ProducerRecord;
import org.apache.kafka.clients.producer.RecordMetadata;

import java.util.List;
import java.util.concurrent.TimeUnit;

/** 同一订单使用稳定键；顺序只在所选分区内成立。 */
public final class Lab {
    public static List<RecordMetadata> publish(
            Producer<String, String> producer, String topic, List<Event> events) throws Exception {
        // 学习区开始
        java.util.ArrayList<RecordMetadata> result = new java.util.ArrayList<>();
        for (Event event : events) {
            result.add(
                    producer.send(new ProducerRecord<>(topic, event.order(), event.encode()))
                            .get(20, TimeUnit.SECONDS));
        }
        return List.copyOf(result);
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
            System.out.println("用法：./gradlew :kafka-01-contract:run -PappArgs=127.0.0.1:19092");
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

n条事件按顺序发送，应用循环O(n)、保存确认结果O(n)，瓶颈还包含n次网络确认。替代是有界异步批量并保留按分区顺序与错误聚合。

## 面试问题、标准回答与追问

### 问题1：Kafka 保证全局有序吗？

标准回答：只保证单分区日志顺序。跨分区读取和异步业务完成先后都不能直接推导全局顺序。需要全局顺序时单分区会限制吞吐，也可使用业务序号和重排。

追问练习：用本节一个具体测试、状态或故障窗口支撑回答；如果删除前提，构造反例。

### 问题2：offset=7 代表已完成第7条吗？

标准回答：不一定。消费者 position 是下次读取位置，committed 是恢复起点，业务是否成功是第三个状态。提交7意味着从7开始恢复。

追问练习：用本节一个具体测试、状态或故障窗口支撑回答；如果删除前提，构造反例。

### 问题3：扩分区为什么会影响同key顺序？

标准回答：默认哈希对分区数取模改变，旧消息和新消息可能位于不同分区；迁移需要排空、版本路由或业务序号约束。

追问练习：用本节一个具体测试、状态或故障窗口支撑回答；如果删除前提，构造反例。

### 问题4：消费者数量超过分区数有用吗？

标准回答：同组中多出的消费者可能空闲。它能作为故障备用，但不会凭空增加该topic消费并行度。

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
