# C09-03 实体内顺序、延迟投递与迟到事件

## 企业场景与学习目标

同一订单的创建、支付、发货必须有序处理，同时未支付订单需要超时关闭。不同订单应能并行；支付成功后的迟到取消事件不能把订单取消。

本节范围：先运行完整作者实现，再在 Academy 预览的占位区独立编码，最后对照公开标准解。预计 60–100 分钟；先修不足请回到首页给出的课程。容器测试目前是可执行待云端 Docker 实证，不代表已经运行成功。

## 概念、机制与图解

FIFO主题要求messageGroup，顺序范围是消息组，发送也需串行；失败可能阻塞同组后续消息。DELAY主题按deliveryTimestamp安排可投递时间，并不保证消费者在那一刻完成业务。晚到、重复、系统时间误差均须纳入状态机。cancelIfUnpaid是教学纯模型，生产实现应在数据库用WHERE status=UNPAID原子更新。

```text
FIFO组order1: 创建 -> 支付 -> 发货
FIFO组order2: 创建 -> 取消
DELAY超时事件 -> [当前仍未支付?] --是--> 条件更新取消
                                  \--否--> 保留已支付状态
```

## 一步一步运行、编码与验证

在课程根目录执行，不要在 task 子目录运行。所有数据是随机命名的合成课堂资源。

```bash
./gradlew :rocketmq-03-order-delay:test
./gradlew :rocketmq-03-order-delay:test -PwithDocker
./gradlew :rocketmq-03-order-delay:run
```

1. 运行LabTest，检查同实体messageGroup以及已支付/已取消的幂等边界
2. 运行BrokerTest，创建FIFO主题+顺序组，串行发送三个序号，逐条接收确认并断言1/2/3
3. 创建DELAY主题并发出6秒后可见事件，核对实际接收时刻不早于计划，不使用准点上界假设
4. 实现ordered让相同订单使用相同group；不要把全topic塞入唯一组假装可扩展
5. 独立用SQL条件更新替代纯状态模型，加入支付与取消并发竞争的可见测试

默认命令只跑无容器用例；带 -PwithDocker 才会启动真实服务。无 Docker 时后者必须失败，不使用 disabledWithoutDocker 自动跳过来制造全绿。第一次依赖下载失败属于环境问题，先检查 Maven Central 与 Wrapper 下载；API 或断言失败再按中文提示检查代码。

## 本节输入与预期结果

同o1的FIFO序号依次为1/2/3；DELAY的expire1不早于对齐后的计划时刻接收；对PAID执行取消仍返回PAID，重复取消CANCELLED仍为CANCELLED。

## 完整调用示例

src/labs/messaging/Usage.java 是可见命令行调用端；无参数打印准确参数说明，有参数连接明确指定的课堂端点。BrokerTest.java 是本节专用业务调用链，展示正常和故障路径；所有测试都在 test/ 中公开。公共 Event、Inbox 与容器夹具在课程根 support/src/labs/messaging/，不依赖作者机器的私有文件。

## 真实源码阅读与断点路线

固定源码：[rocketmq rocketmq-all-5.3.2：proxy/src/main/java/org/apache/rocketmq/proxy/grpc/v2/producer/SendMessageActivity.java](https://github.com/apache/rocketmq/blob/2baaf044ea9b12a73a89433242b7b7c56a1b89c2/proxy/src/main/java/org/apache/rocketmq/proxy/grpc/v2/producer/SendMessageActivity.java)

固定提交：2baaf044ea9b12a73a89433242b7b7c56a1b89c2。目标符号：sendMessage。关注消息类型校验、messageGroup和deliveryTimestamp映射，再沿Broker存储/TimerMessageStore阅读；用NORMAL主题发FIFO或DELAY构造协议负例。

按入口→关键状态→条件分支→可观察结果阅读；记录一次正常路径和一次失败路径。断点可对官方 sources JAR 附源码调试；本次没有伪造断点截图。support/ 与 Lab 中的自写模型不是上游源码替身。不要从一个模型断言生产系统所有故障都被覆盖。

## 标准答案与逐步解析

先明确消息组与主题消息类型，避免普通主题无group也宣称有序。测试每条确认后再收下一条，隔离顺序保证和并行业务完成顺序。延迟测试允许投递更晚，不允许更早；业务状态判断始终以当前持久事实为准。本地枚举状态机时间/空间O(1)，仅用于说明逻辑边界，不提供持久化或跨实例互斥。

下方为与工程同源的完整实现及调用方，不隐藏答案。先自己完成再读；已读答案后需换条件盲做才能判断掌握程度。

### Lab.java

```java
package labs.messaging;

import org.apache.rocketmq.client.apis.message.Message;

import java.nio.charset.StandardCharsets;

public final class Lab {
    public enum OrderState {
        UNPAID,
        PAID,
        CANCELLED
    }

    public static Message ordered(String topic, Event event) {
        // 学习区开始
        return RocketClient.PROVIDER
                .newMessageBuilder()
                .setTopic(topic)
                .setKeys(event.id())
                .setMessageGroup(event.order())
                .setBody(event.encode().getBytes(StandardCharsets.UTF_8))
                .build();
        // 学习区结束
    }

    public static Message delayed(String topic, Event event, long deliveryTimestamp) {
        return RocketClient.PROVIDER
                .newMessageBuilder()
                .setTopic(topic)
                .setKeys(event.id())
                .setDeliveryTimestamp(deliveryTimestamp)
                .setBody(event.encode().getBytes(StandardCharsets.UTF_8))
                .build();
    }

    /** 迟到的超时事件不得把已支付订单改成取消；生产环境使用数据库条件更新。 */
    public static OrderState cancelIfUnpaid(OrderState state) {
        return state == OrderState.UNPAID ? OrderState.CANCELLED : state;
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
            System.out.println("用法：./gradlew :rocketmq-03-order-delay:run -PappArgs='127.0.0.1:18081 课堂主题'");
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

构造消息O(B)，纯取消状态机O(1)；服务器定时与FIFO存储不能由该模型推断复杂度。替代是数据库超时扫描或任务调度，需要比较扫描成本、时延与状态竞争。

## 面试问题、标准回答与追问

### 问题1：相同key是否自动就是FIFO组？

标准回答：不是。5.x明确使用messageGroup；业务key用于关联，不能偷换成顺序分组字段。

追问练习：用本节一个具体测试、状态或故障窗口支撑回答；如果删除前提，构造反例。

### 问题2：为什么顺序消费失败会拖慢后续？

标准回答：若先处理后续事件可能破坏同组序列，因此必须在正确性与可用性之间定义阻塞、重试、隔离和业务补偿策略。

追问练习：用本节一个具体测试、状态或故障窗口支撑回答；如果删除前提，构造反例。

### 问题3：定时消息等于定时任务准点执行吗？

标准回答：不等于，它是服务端可投递时机；积压、网络、消费者状态与业务处理都会增加延迟。

追问练习：用本节一个具体测试、状态或故障窗口支撑回答；如果删除前提，构造反例。

### 问题4：取消事件迟到怎么处理？

标准回答：读取或原子检查当前业务状态，已支付不再取消，已取消重复执行无影响；不要只信事件中的旧状态。

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
