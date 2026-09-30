# C08-02 生产端确认、重试与幂等

## 企业场景与学习目标

订单提交后发送通知，调用超时导致上游再次提交同一业务事件。目标是承认结果未知，并以稳定事件ID处理业务重发，不能把生产者幂等当作业务唯一约束。

本节范围：先运行完整作者实现，再在 Academy 预览的占位区独立编码，最后对照公开标准解。预计 60–100 分钟；先修不足请回到首页给出的课程。本节真实容器与正反解的已验证提交、环境和证据见课程根目录的验证报告；CLI/CI通过不代替Academy界面与归档验收。

## 概念、机制与图解

acks=0 不等确认，acks=1 等leader，acks=all 等当前ISR满足条件后的确认。min.insync.replicas 与副本数、ISR和刷盘是不同层。幂等生产利用 producer id/epoch 与分区序列抵御协议重试，应用调用两次send仍是两条。delivery.timeout.ms 是有界等待预算，超时不总能证明broker没有写入。

```text
业务调用 --send(e1)--> 序号0 --重试同序号--> broker去重
再次调用 --send(e1)--> 序号1 -------------> broker接受
                         |
                    业务ID去重属于应用
```

## 一步一步运行、编码与验证

在课程根目录执行，不要在 task 子目录运行。所有数据是随机命名的合成课堂资源。

```bash
./gradlew :kafka-02-producer:test
./gradlew :kafka-02-producer:test -PwithDocker
./gradlew :kafka-02-producer:run
```

1. 运行配置单测，检查acks、幂等及in-flight约束
2. 运行BrokerTest，同一个event ID发送两次，断言真实broker里有两条记录
3. 删掉幂等配置或改acks=0，观察配置冲突负例，而不是允许静默降级
4. 修改调用端处理Future异常：记录事件ID、结果未知状态和重试预算；禁止无限循环重试

默认命令只跑无容器用例；带 -PwithDocker 才会启动真实服务。无 Docker 时后者必须失败，不使用 disabledWithoutDocker 自动跳过来制造全绿。第一次依赖下载失败属于环境问题，先检查 Maven Central 与 Wrapper 下载；API 或断言失败再按中文提示检查代码。

## 本节输入与预期结果

同event ID连续两次send：broker记录数=2，业务ID去重后种类数=1；将acks改0且保留显式幂等，构造客户端必须报配置冲突。

## 完整调用示例

src/labs/messaging/Usage.java 是可见命令行调用端；无参数打印准确参数说明，有参数连接明确指定的课堂端点。BrokerTest.java 是本节专用业务调用链，展示正常和故障路径；所有测试都在 test/ 中公开。公共 Event、Inbox 与容器夹具在课程根 support/src/labs/messaging/，不依赖作者机器的私有文件。

## 真实源码阅读与断点路线

固定源码：[kafka 3.9.1：clients/src/main/java/org/apache/kafka/clients/producer/internals/Sender.java](https://github.com/apache/kafka/blob/f745dfdcee2b9851204ddbbcd423626ab87294bc/clients/src/main/java/org/apache/kafka/clients/producer/internals/Sender.java)

固定提交：f745dfdcee2b9851204ddbbcd423626ab87294bc。目标符号：completeBatch。沿sendProducerData→sendProduceRequests→handleProduceResponse→completeBatch检查可重试错误、delivery过期和序列状态；断点观察同batch重试与新send差异。

按入口→关键状态→条件分支→可观察结果阅读；记录一次正常路径和一次失败路径。断点可对官方 sources JAR 附源码调试；本次没有伪造断点截图。support/ 与 Lab 中的自写模型不是上游源码替身。不要从一个模型断言生产系统所有故障都被覆盖。

## 标准答案与逐步解析

可靠配置成组设置，并让业务事件ID贯穿重发。acks=all 在单副本课堂中只有一个ISR，不能借这个结果宣称高可用；第六节三副本用例才观察节点故障。Future异常需要上交业务补偿流程。不要生成新事件ID来重试同一件业务，否则下游唯一键失去意义。

下方为与工程同源的完整实现及调用方，不隐藏答案。先自己完成再读；已读答案后需换条件盲做才能判断掌握程度。

### Lab.java

```java
package labs.messaging;

import org.apache.kafka.clients.producer.ProducerConfig;

import java.util.Properties;

/** 确认、幂等和有界等待必须一起配置。 */
public final class Lab {
    public static Properties reliable(String bootstrap) {
        // 学习区开始
        Properties config = KafkaSupport.producerProperties(bootstrap);
        config.put(ProducerConfig.ACKS_CONFIG, "all");
        config.put(ProducerConfig.ENABLE_IDEMPOTENCE_CONFIG, "true");
        config.put(ProducerConfig.MAX_IN_FLIGHT_REQUESTS_PER_CONNECTION, "5");
        return config;
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
            System.out.println("用法：./gradlew :kafka-02-producer:run -PappArgs=127.0.0.1:19092");
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

配置构造O(1)，实际发送受批量、压缩、分区与网络支配，不能从这段代码估计生产吞吐。替代是有界异步确认，并由稳定业务ID和消费inbox兜底。

## 面试问题、标准回答与追问

### 问题1：acks=all等于每次磁盘fsync吗？

标准回答：不等于。它描述副本确认条件；Kafka依赖复制与操作系统页缓存等机制，不能把此参数直接解释为每次物理落盘。

追问练习：用本节一个具体测试、状态或故障窗口支撑回答；如果删除前提，构造反例。

### 问题2：生产者幂等能覆盖重启和应用重发吗？

标准回答：不能把所有重启场景与业务重发归为同一个序列。相同业务ID两次send的真实测试展示两条记录；业务去重必须有独立约束。

追问练习：用本节一个具体测试、状态或故障窗口支撑回答；如果删除前提，构造反例。

### 问题3：为什么超时是结果未知？

标准回答：请求可能已经写入而响应丢失，也可能尚未写入。应记录稳定业务标识并允许重试后去重，不能直接标为永久失败。

追问练习：用本节一个具体测试、状态或故障窗口支撑回答；如果删除前提，构造反例。

### 问题4：吞吐提升的代价是什么？

标准回答：批量、压缩和异步并行能减少开销，但增加等待/内存/背压管理复杂度；必须以消息大小、分区数、延迟分布和错误率评测。

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
