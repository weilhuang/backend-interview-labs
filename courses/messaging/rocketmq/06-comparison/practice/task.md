# C09-06 共同契约、恢复证据与选型评审

## 企业场景与学习目标

同一订单平台评估Kafka与RocketMQ，团队不能仅凭营销词或单次吞吐排名决定。给定业务顺序、延迟消息、回放、事务范围与运维能力，形成带前提的选型结论。

本节范围：先运行完整作者实现，再在 Academy 预览的占位区独立编码，最后对照公开标准解。预计 60–100 分钟；先修不足请回到首页给出的课程。本节真实容器与正反解的已验证提交、环境和证据见课程根目录的验证报告；CLI/CI通过不代替Academy界面与归档验收。

## 概念、机制与图解

两路都以Event.id/order/sequence/cents为契约；重复应用发送在两种broker里都会存在。对照模型按稳定ID去重，真实broker测试验证输入可见条数与最终业务不变量。模型是进程内算法，不替代第三/第四节MySQL持久inbox。不要求先学Kafka：测试已经提供全部调用，若不运行必须标明未亲测。

```text
同一事件e1 x2 -> Kafka真实日志   -> 契约解析 -> 幂等模型 -> 100
同一事件e1 x2 -> RocketMQ真实主题 -> 契约解析 -> 幂等模型 -> 100
             比较顺序范围/回放/事务边界/成本，不能据此比较吞吐
```

## 一步一步运行、编码与验证

在课程根目录执行，不要在 task 子目录运行。所有数据是随机命名的合成课堂资源。

```bash
./gradlew :rocketmq-06-comparison:test
./gradlew :rocketmq-06-comparison:test -PwithDocker
./gradlew :rocketmq-06-comparison:run
```

1. 运行LabTest验证重复拒绝与金额溢出不污染已处理集合
2. 运行BrokerTest先后创建两种真实broker，分别发送两次相同事件ID并收两条
3. 实现accept，保证重复不再次累加；溢出时撤销刚写入的去重状态
4. 将模型换成持久Inbox并添加消费者重建测试，不能拿本节Set冒充生产幂等
5. 写一页评审：业务必须项、两方案达标证据、尚未验证风险、容量实验计划与迁移回滚

默认命令只跑无容器用例；带 -PwithDocker 才会启动真实服务。无 Docker 时后者必须失败，不使用 disabledWithoutDocker 自动跳过来制造全绿。第一次依赖下载失败属于环境问题，先检查 Maven Central 与 Wrapper 下载；API 或断言失败再按中文提示检查代码。

## 本节输入与预期结果

同一100分事件各向两种broker发送两次，两路真实记录数都为2，去重模型结果都为100；Long.MAX_VALUE再加1必须抛溢出异常且总额不变。

## 完整调用示例

src/labs/messaging/Usage.java 是可见命令行调用端；无参数打印准确参数说明，有参数连接明确指定的课堂端点。BrokerTest.java 是本节专用业务调用链，展示正常和故障路径；所有测试都在 test/ 中公开。公共 Event、Inbox 与容器夹具在课程根 support/src/labs/messaging/，不依赖作者机器的私有文件。

## 真实源码阅读与断点路线

固定源码：[rocketmq rocketmq-all-5.3.2：proxy/src/main/java/org/apache/rocketmq/proxy/grpc/v2/consumer/AckMessageActivity.java](https://github.com/apache/rocketmq/blob/2baaf044ea9b12a73a89433242b7b7c56a1b89c2/proxy/src/main/java/org/apache/rocketmq/proxy/grpc/v2/consumer/AckMessageActivity.java)

固定提交：2baaf044ea9b12a73a89433242b7b7c56a1b89c2。目标符号：ackMessage。对照消息确认路径与Kafka ConsumerCoordinator.commitOffsetsSync，解释单消息确认和分区位点恢复的不同表示，不把API相似当相同保证。

按入口→关键状态→条件分支→可观察结果阅读；记录一次正常路径和一次失败路径。断点可对官方 sources JAR 附源码调试；本次没有伪造断点截图。support/ 与 Lab 中的自写模型不是上游源码替身。不要从一个模型断言生产系统所有故障都被覆盖。

## 标准答案与逐步解析

共同业务合同是相同输入和最终效果，不是要求两种队列底层协议一样。两路顺序执行容器测试限制资源占用；比较得到的100仅证明示例去重模型作用，不形成吞吐结论。Math.addExact避免静默溢出，失败移除seen避免永久漏处理；真实数据库需同事务实现同一性质。平均Set操作O(1)，空间O(去重事件数)，保留策略必须与重放窗口匹配。

下方为与工程同源的完整实现及调用方，不隐藏答案。先自己完成再读；已读答案后需换条件盲做才能判断掌握程度。

### Lab.java

```java
package labs.messaging;

import java.util.HashSet;
import java.util.Set;

/** 进程内对照模型，只验证消息契约与幂等算法，不能替代数据库持久化。 */
public final class Lab {
    private final Set<String> seen = new HashSet<>();
    private long total;

    public synchronized boolean accept(Event event) {
        // 学习区开始
        if (!seen.add(event.id())) return false;
        try {
            total = Math.addExact(total, event.cents());
            return true;
        } catch (ArithmeticException overflow) {
            seen.remove(event.id());
            throw overflow;
        }
        // 学习区结束
    }

    public synchronized long total() {
        return total;
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
            System.out.println("用法：./gradlew :rocketmq-06-comparison:run -PappArgs='127.0.0.1:18081 课堂主题'");
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

n次处理平均O(n)，去重空间O(u)，u为不同事件ID数量；HashSet极端分布与并发竞争需另测。替代是数据库持久inbox，成本更高但能跨进程恢复。

## 面试问题、标准回答与追问

### 问题1：什么时候更倾向Kafka？

标准回答：如果核心约束是分区日志、可回放流处理和Kafka生态，应验证分区/保留/消费组/事务条件；这是基于需求和团队能力的选择，不是绝对优劣。

追问练习：用本节一个具体测试、状态或故障窗口支撑回答；如果删除前提，构造反例。

### 问题2：什么时候更倾向RocketMQ？

标准回答：若需要明确的业务消息类型、延迟/FIFO/事务回查语义，应验证所选版本与客户端的真实约束和恢复操作，再估计团队运维成本。

追问练习：用本节一个具体测试、状态或故障窗口支撑回答；如果删除前提，构造反例。

### 问题3：两者事务保证能直接对等比较吗？

标准回答：不能。Kafka内read-process-write的输出与位点事务，和RocketMQ关联本地事务与消息投递的机制，解决的边界不同；外部副作用都要单独设计。

追问练习：用本节一个具体测试、状态或故障窗口支撑回答；如果删除前提，构造反例。

### 问题4：如何做可信容量评测？

标准回答：固定硬件、版本、消息大小、副本/刷盘/acks、批量、压缩、分区/队列数和失败率，比较p95/p99与吞吐及恢复时间，公开统计方法与瓶颈。

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
