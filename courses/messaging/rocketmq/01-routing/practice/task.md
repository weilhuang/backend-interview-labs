# C09-01 消息模型、路由与完整调用

## 企业场景与学习目标

订单服务异步通知仓储和审计，两组都需要完整事件流。先修C04/C06，不要求先学Kafka。本课选择RocketMQ5.3.2的Proxy+Java gRPC SDK5.0.8，避免把Remoting旧API与新协议混讲。

本节范围：先运行完整作者实现，再在 Academy 预览的占位区独立编码，最后对照公开标准解。预计 60–100 分钟；先修不足请回到首页给出的课程。容器测试目前是可执行待云端 Docker 实证，不代表已经运行成功。

## 概念、机制与图解

NameServer保存broker路由，Broker存储消息，Proxy给gRPC客户端提供接入。topic按类型建模，tag用于订阅过滤，key用于业务查询/追踪但不是去重约束。消费组决定逻辑订阅进度；多个独立组各取一份。同组扩容是竞争工作，不是广播。

```text
订单Java gRPC -> 随机映射端口 -> Proxy8081
                                   |
               NameServer9876 <-- Broker10911 -> CommitLog
                                   |
                              仓储组 / 审计组
```

## 一步一步运行、编码与验证

在课程根目录执行，不要在 task 子目录运行。所有数据是随机命名的合成课堂资源。

```bash
./gradlew :rocketmq-01-routing:test
./gradlew :rocketmq-01-routing:test -PwithDocker
./gradlew :rocketmq-01-routing:run
```

1. 运行LabTest，检查topic/key/tag和完整事件体
2. 运行BrokerTest：自动创建NORMAL主题与两个独立消费组，真实发送同一事件，比较messageId和payload
3. 实现Lab.publish，只发送调用方给定事件；禁止用新随机ID掩盖应用重试
4. 用Usage指定课堂Proxy与预建NORMAL主题发送，按文档检查容器内topic状态
5. 阅读Proxy的RouteActivity分支，解释为什么端口映射不是只写一个-p参数就足够

默认命令只跑无容器用例；带 -PwithDocker 才会启动真实服务。无 Docker 时后者必须失败，不使用 disabledWithoutDocker 自动跳过来制造全绿。第一次依赖下载失败属于环境问题，先检查 Maven Central 与 Wrapper 下载；API 或断言失败再按中文提示检查代码。

## 本节输入与预期结果

e1发送返回一个messageId；仓储/审计两个独立组各读到同一messageId、tag=order和相同的100分事件。

## 完整调用示例

src/labs/messaging/Usage.java 是可见命令行调用端；无参数打印准确参数说明，有参数连接明确指定的课堂端点。BrokerTest.java 是本节专用业务调用链，展示正常和故障路径；所有测试都在 test/ 中公开。公共 Event、Inbox 与容器夹具在课程根 support/src/labs/messaging/，不依赖作者机器的私有文件。

## 真实源码阅读与断点路线

固定源码：[rocketmq rocketmq-all-5.3.2：proxy/src/main/java/org/apache/rocketmq/proxy/grpc/v2/route/RouteActivity.java](https://github.com/apache/rocketmq/blob/2baaf044ea9b12a73a89433242b7b7c56a1b89c2/proxy/src/main/java/org/apache/rocketmq/proxy/grpc/v2/route/RouteActivity.java)

固定提交：2baaf044ea9b12a73a89433242b7b7c56a1b89c2。目标符号：convertToAddressList。观察request.endpoints、useEndpointPortFromRequest和grpcServerPort两个分支；再向QueryRoute的broker endpoints映射追踪，不能用Linux容器IP偷偷绕过Mac问题。

按入口→关键状态→条件分支→可观察结果阅读；记录一次正常路径和一次失败路径。断点可对官方 sources JAR 附源码调试；本次没有伪造断点截图。support/ 与 Lab 中的自写模型不是上游源码替身。不要从一个模型断言生产系统所有故障都被覆盖。

## 标准答案与逐步解析

使用5.x ClientServiceProvider构建producer，回收close资源。Fixture明确创建主题类型与消费组，管理命令在容器内运行；客户端仅访问映射后的gRPC端点。RocketMQ5.3.2默认useEndpointPortFromRequest=false会把路由端口替换为8081，夹具显式true保留请求端口。此设计按源码验证，Mac/Linux动态验证尚未执行。 官方mqadmin捕获异常后可能退出零，因此夹具通过RocketAdminResult检查实际命令成功输出与异常堆栈，不用退出码冒充协议就绪。

下方为与工程同源的完整实现及调用方，不隐藏答案。先自己完成再读；已读答案后需换条件盲做才能判断掌握程度。

### Lab.java

```java
package labs.messaging;

import org.apache.rocketmq.client.apis.producer.Producer;
import org.apache.rocketmq.client.apis.producer.SendReceipt;

public final class Lab {
    public static SendReceipt publish(Producer producer, String topic, Event event)
            throws Exception {
        // 学习区开始
        return producer.send(RocketClient.message(topic, event));
        // 学习区结束
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
            System.out.println("用法：./gradlew :rocketmq-01-routing:run -PappArgs='127.0.0.1:18081 课堂主题'");
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

序列化与消息字节长度B成正比，持有一条消息O(B)；确认延迟取决于代理、存储和配置。替代是复用producer加有界异步发送，不要每条新建连接。

## 面试问题、标准回答与追问

### 问题1：key与messageId有什么区别？

标准回答：key是业务设置的索引/关联标识，messageId由消息系统生成。相同key不意味着broker拒绝第二条发送，消费幂等应使用稳定业务ID和持久唯一约束。

追问练习：用本节一个具体测试、状态或故障窗口支撑回答；如果删除前提，构造反例。

### 问题2：5.x为什么还看到NameServer？

标准回答：本实验Broker仍通过NameServer完成路由注册；应用使用gRPC Proxy接入，并不等于服务端内部所有经典组件消失。

追问练习：用本节一个具体测试、状态或故障窗口支撑回答；如果删除前提，构造反例。

### 问题3：tag能替代独立topic吗？

标准回答：tag用于同主题内过滤，不替代独立保留、消息类型、权限、容量与隔离边界。不同可靠性/运维要求通常需要更明确的划分。

追问练习：用本节一个具体测试、状态或故障窗口支撑回答；如果删除前提，构造反例。

### 问题4：为什么随机映射后连上8081仍消费失败？

标准回答：初始连接不代表路由响应端点可达。需要检查Proxy返回的地址与端口；本夹具启用useEndpointPortFromRequest保留映射端点。

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
