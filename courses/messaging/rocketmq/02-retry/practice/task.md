# C09-02 有界重试、真实重投与隔离队列

## 企业场景与学习目标

库存服务遇到暂时数据库不可用，而另一条订单事件字段永久非法。前者应重试，后者应隔离并告警，不能让毒消息无限占用消费资源。

本节范围：先运行完整作者实现，再在 Academy 预览的占位区独立编码，最后对照公开标准解。预计 60–100 分钟；先修不足请回到首页给出的课程。容器测试目前是可执行待云端 Docker 实证，不代表已经运行成功。

## 概念、机制与图解

本课SimpleConsumer采用主动receive/ack和不可见期。未ack后由服务端重新投递；deliveryAttempt描述投递尝试。临时失败有明确预算，永久失败无需等满全部重试。这里实现的是应用自建隔离主题，不冒充Broker原生%DLQ%消费组死信。原生重试上限/策略由所选版本组配置决定，可用mqadmin updateSubGroup的-r/-p设置并导出对照。 另一个独立NativeDeadLetterTest实际触发Broker原生DLQ，两类路径分别验证，不混称为同一保证。

```text
receive -> 业务成功 -> ack
    |
    +-> 临时失败 -> 不ack -> 不可见期结束 -> 真实重投
    |
    +-> 永久失败/超预算 -> 发送隔离主题 -> 等确认 -> ack原消息
```

## 一步一步运行、编码与验证

在课程根目录执行，不要在 task 子目录运行。所有数据是随机命名的合成课堂资源。

```bash
./gradlew :rocketmq-02-retry:test
./gradlew :rocketmq-02-retry:test -PwithDocker
./gradlew :rocketmq-02-retry:run
```

1. 运行LabTest，覆盖成功、临时失败、最大次数边界、永久失败和非法参数
2. 运行BrokerTest，不ack第一条，等待服务端真正再次投递，比较同messageId且deliveryAttempt增长
3. 实现decide，不允许达到上限仍无限重试；实现或阅读quarantine确认顺序
4. 运行NativeDeadLetterTest：用所选版本-r/-p明确把该随机组配置为一次重试，自始至终不ack，最后用容器内printMsg核验%DLQ%组名中的原始消息体
5. 从隔离主题读出原始事件与原主题，验证不是只打日志就声称入DLQ
6. 独立补：隔离发布成功但原ack失败导致重复，使用第四节持久inbox去重；记录回放入口和告警责任人

默认命令只跑无容器用例；带 -PwithDocker 才会启动真实服务。无 Docker 时后者必须失败，不使用 disabledWithoutDocker 自动跳过来制造全绿。第一次依赖下载失败属于环境问题，先检查 Maven Central 与 Wrapper 下载；API 或断言失败再按中文提示检查代码。

## 本节输入与预期结果

未ack时下一次真实交付messageId不变、deliveryAttempt增加；永久失败进入应用隔离主题并保留原主题。独立原生测试的毒消息最终能从%DLQ%组名读到完整事件。

## 完整调用示例

src/labs/messaging/Usage.java 是可见命令行调用端；无参数打印准确参数说明，有参数连接明确指定的课堂端点。BrokerTest.java 是本节专用业务调用链，展示正常和故障路径；所有测试都在 test/ 中公开。公共 Event、Inbox 与容器夹具在课程根 support/src/labs/messaging/，不依赖作者机器的私有文件。

## 真实源码阅读与断点路线

固定源码：[rocketmq rocketmq-all-5.3.2：broker/src/main/java/org/apache/rocketmq/broker/processor/PopMessageProcessor.java](https://github.com/apache/rocketmq/blob/2baaf044ea9b12a73a89433242b7b7c56a1b89c2/broker/src/main/java/org/apache/rocketmq/broker/processor/PopMessageProcessor.java)

固定提交：2baaf044ea9b12a73a89433242b7b7c56a1b89c2。目标符号：processRequest。读取POP取消息、不可见期、重试主题与receipt handle相关路径；与AckMessageProcessor对照。不要把DefaultMQPushConsumer的Remoting重试参数原封不动当成gRPC SimpleConsumer合同。

按入口→关键状态→条件分支→可观察结果阅读；记录一次正常路径和一次失败路径。断点可对官方 sources JAR 附源码调试；本次没有伪造断点截图。support/ 与 Lab 中的自写模型不是上游源码替身。不要从一个模型断言生产系统所有故障都被覆盖。

## 标准答案与逐步解析

按错误可恢复性分类，attempt从1开始。隔离发送等待成功后再ack原消息，否则隔离失败加提前ack会丢数据。即使两个步骤都正确仍有隔离成功、原ack失败的重复窗口，隔离消费者也要去重。BrokerTest使用真实不可见期重投，不是调用两次本地方法伪造重试。应用策略与Broker兜底原生DLQ是两层，不能称为同一个配置。 原生DLQ实验仅对随机课堂DLQ开放读取权限，方便mqadmin读取原文；它验证的是Broker消费组重试上限，不借应用主动发送代替服务端转移。

下方为与工程同源的完整实现及调用方，不隐藏答案。先自己完成再读；已读答案后需换条件盲做才能判断掌握程度。

### Lab.java

```java
package labs.messaging;

import org.apache.rocketmq.client.apis.consumer.SimpleConsumer;
import org.apache.rocketmq.client.apis.message.MessageView;
import org.apache.rocketmq.client.apis.producer.Producer;

public final class Lab {
    public enum Failure {
        NONE,
        TRANSIENT,
        PERMANENT
    }

    public enum Action {
        ACK,
        RETRY,
        QUARANTINE
    }

    public static Action decide(Failure failure, int attempt, int maxAttempts) {
        // 学习区开始
        if (attempt < 1 || maxAttempts < 1) throw new IllegalArgumentException("尝试次数必须为正数");
        if (failure == Failure.NONE) return Action.ACK;
        if (failure == Failure.PERMANENT || attempt >= maxAttempts) return Action.QUARANTINE;
        return Action.RETRY;
        // 学习区结束
    }

    public static void quarantine(
            Producer producer,
            SimpleConsumer consumer,
            MessageView original,
            String deadLetterTopic)
            throws Exception {
        var buffer = original.getBody().duplicate();
        byte[] body = new byte[buffer.remaining()];
        buffer.get(body);
        producer.send(
                RocketClient.PROVIDER
                        .newMessageBuilder()
                        .setTopic(deadLetterTopic)
                        .setKeys(original.getKeys().toArray(String[]::new))
                        .setTag("invalid")
                        .addProperty("原始主题", original.getTopic())
                        .addProperty("错误类型", "永久业务错误")
                        .setBody(body)
                        .build());
        // 必须确认隔离消息发布成功后才能确认原消息。
        consumer.ack(original);
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
            System.out.println("用法：./gradlew :rocketmq-02-retry:run -PappArgs='127.0.0.1:18081 课堂主题'");
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

决策O(1)，隔离复制消息体O(B)；重试次数放大服务端和下游负载。替代可用Broker原生DLQ兜底，应用隔离提供更丰富的业务分类，但必须分别治理确认窗口。

## 面试问题、标准回答与追问

### 问题1：所有异常都应该重试吗？

标准回答：格式/权限/永久业务约束失败通常不会靠重试恢复；应隔离、修复或人工决策。网络超时和临时依赖失败也要有预算与退避。

追问练习：用本节一个具体测试、状态或故障窗口支撑回答；如果删除前提，构造反例。

### 问题2：重投就是业务执行重复吗？

标准回答：重投只是交付层现象，业务是否重复取决于持久幂等。消费副作用成功但ack丢失会重投，需要按事件ID去重。

追问练习：用本节一个具体测试、状态或故障窗口支撑回答；如果删除前提，构造反例。

### 问题3：为什么不能先ack再发隔离队列？

标准回答：发送隔离消息可能失败，原消息已确认后无法靠普通重投恢复，造成消息丢失窗口。

追问练习：用本节一个具体测试、状态或故障窗口支撑回答；如果删除前提，构造反例。

### 问题4：原生DLQ与本课隔离主题有什么不同？

标准回答：原生DLQ由Broker根据消费组重试上限等规则产生，名称/机制与版本有关；本课应用隔离主题能记录业务原因和自定义治理，但必须自己处理发布和ack窗口。

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
