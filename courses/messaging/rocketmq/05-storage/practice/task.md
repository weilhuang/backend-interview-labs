# C09-05 存储路径、刷盘确认与故障恢复

## 企业场景与学习目标

课堂broker需要维护重启。要确认已应答消息恢复后可消费，并区分进程退出、磁盘损坏、副本故障三个不同模型。

本节范围：先运行完整作者实现，再在 Academy 预览的占位区独立编码，最后对照公开标准解。预计 60–100 分钟；先修不足请回到首页给出的课程。容器测试目前是可执行待云端 Docker 实证，不代表已经运行成功。

## 概念、机制与图解

CommitLog保存消息实体；ConsumeQueue保存面向逻辑队列的索引，索引与实体不是两份独立完整副本。同步/异步刷盘与主从复制分别约束不同故障窗口。单broker的SYNC_FLUSH实验只能观察同磁盘重启，不提供跨节点容灾。

```text
发送 -> CommitLog追加 -> SYNC_FLUSH确认
                |
           ConsumeQueue索引 -> 消费者
                |
   容器restart保留同一写层 -> 恢复已确认消息
   删除写层/磁盘损坏       -> 本实验不提供副本恢复保证
```

## 一步一步运行、编码与验证

在课程根目录执行，不要在 task 子目录运行。所有数据是随机命名的合成课堂资源。

```bash
./gradlew :rocketmq-05-storage:test
./gradlew :rocketmq-05-storage:test -PwithDocker
./gradlew :rocketmq-05-storage:run
```

1. 运行模型单测，明确标注它只解释确认边界，不是真刷盘实现
2. 运行BrokerTest，向真实broker发送消息并等待确认
3. 实现Lab.missing：按已获得发送确认的业务ID核对恢复记录，重复投递不能抵消另一条消息缺失，并按ID稳定排序报告
4. 使用容器内find观察真实commitlog文件，restart同一个容器保留写层
5. 重新等待映射端口与topicStatus真实就绪，再重建消费者断言原事件可读
6. 独立对照ASYNC_FLUSH配置并记录能观察和不能证明的结论；不能把一次数据仍在当作断电零丢失

默认命令只跑无容器用例；带 -PwithDocker 才会启动真实服务。无 Docker 时后者必须失败，不使用 disabledWithoutDocker 自动跳过来制造全绿。第一次依赖下载失败属于环境问题，先检查 Maven Central 与 Wrapper 下载；API 或断言失败再按中文提示检查代码。

## 本节输入与预期结果

确认disk1后观察到真实commitlog文件；重启同一容器并重建消费者后仍读到disk1；同步刷盘且仅1副本的模型报告单机磁盘风险。

## 完整调用示例

src/labs/messaging/Usage.java 是可见命令行调用端；无参数打印准确参数说明，有参数连接明确指定的课堂端点。BrokerTest.java 是本节专用业务调用链，展示正常和故障路径；所有测试都在 test/ 中公开。公共 Event、Inbox 与容器夹具在课程根 support/src/labs/messaging/，不依赖作者机器的私有文件。

## 真实源码阅读与断点路线

固定源码：[rocketmq rocketmq-all-5.3.2：store/src/main/java/org/apache/rocketmq/store/CommitLog.java](https://github.com/apache/rocketmq/blob/2baaf044ea9b12a73a89433242b7b7c56a1b89c2/store/src/main/java/org/apache/rocketmq/store/CommitLog.java)

固定提交：2baaf044ea9b12a73a89433242b7b7c56a1b89c2。目标符号：asyncPutMessage。从追加到handleDiskFlush与复制确认路径逐项画等待条件；再查看DefaultMessageStore分发与ConsumeQueue索引更新，区分同步刷盘配置和复制配置。

按入口→关键状态→条件分支→可观察结果阅读；记录一次正常路径和一次失败路径。断点可对官方 sources JAR 附源码调试；本次没有伪造断点截图。support/ 与 Lab 中的自写模型不是上游源码替身。不要从一个模型断言生产系统所有故障都被覆盖。

## 标准答案与逐步解析

测试先等待send返回，再restart同容器，验证真实消息体。restart保留容器文件系统，这与stop并创建新容器不是同一故障；课程结束close会清理实验写层。SYNC_FLUSH说明刷盘等待路径，不承诺单盘损坏仍可用。risk方法是显式标注的纯教学模型，时间空间O(1)，不伪装成RocketMQ存储源码。 missing把恢复记录的业务ID放入Set，再检查每个已确认ID，重复记录不会抵消另一个ID缺失；真实重启测试使用这个核验器。

下方为与工程同源的完整实现及调用方，不隐藏答案。先自己完成再读；已读答案后需换条件盲做才能判断掌握程度。

### Lab.java

```java
package labs.messaging;

import java.util.HashSet;
import java.util.List;
import java.util.Set;

public final class Lab {
    /** 对照已获得发送确认的业务ID与恢复后的读取结果，重复投递不能掩盖缺失。 */
    public static List<String> missing(Set<String> acknowledged, List<Event> recovered) {
        // 学习区开始
        Set<String> actual = new HashSet<>();
        for (Event event : recovered) actual.add(event.id());
        return acknowledged.stream().filter(id -> !actual.contains(id)).sorted().toList();
        // 学习区结束
    }

    /** 这是确认边界教学模型，不是RocketMQ刷盘或复制源码。 */
    public record Durability(boolean synchronousFlush, int acknowledgedReplicas) {}

    public static String risk(Durability durability) {
        if (durability.acknowledgedReplicas() < 1) throw new IllegalArgumentException("副本数至少为一");
        if (!durability.synchronousFlush()) return "进程已确认仍可能存在未刷盘窗口";
        if (durability.acknowledgedReplicas() == 1) return "已同步刷盘但仍有单机磁盘故障风险";
        return "已满足声明副本确认数，仍需验证故障域与恢复";
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
            System.out.println("用法：./gradlew :rocketmq-05-storage:run -PappArgs='127.0.0.1:18081 课堂主题'");
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

恢复核验对r条恢复记录、a个已确认ID和m个缺失ID，平均时间O(r+a+m log m)，空间O(r+m)。risk纯教学函数O(1)，不能据此推断CommitLog、fsync或恢复扫描成本。替代是持久化确认清单并在多副本恢复后逐批审计，不能仅比较记录条数。

## 面试问题、标准回答与追问

### 问题1：有ConsumeQueue是否就有第二份消息备份？

标准回答：不是，它通常是索引性质的数据结构，消息实体在CommitLog；副本策略与索引必须分别讨论。

追问练习：用本节一个具体测试、状态或故障窗口支撑回答；如果删除前提，构造反例。

### 问题2：同步刷盘可以替代复制吗？

标准回答：不可以，它解决本机写入确认的一部分窗口，磁盘和主机故障域仍可能不可用或丢失，需要复制和恢复策略。

追问练习：用本节一个具体测试、状态或故障窗口支撑回答；如果删除前提，构造反例。

### 问题3：restart成功能推出断电不丢吗？

标准回答：不能。优雅/超时停止、内核缓存、磁盘持久性和突然断电不同；这里只声明同容器重启场景。

追问练习：用本节一个具体测试、状态或故障窗口支撑回答；如果删除前提，构造反例。

### 问题4：重启后消费不到先查什么？

标准回答：先检查broker/Proxy/路由健康，再查topic状态与消费组位点，再检查保留与存储路径；不要先删除数据重建来抹掉证据。

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
