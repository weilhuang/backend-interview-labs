# C07-07 有界缓存服务与故障演练

## 企业场景与进入条件

订单读接口通常命中Redis，但Redis可能不可用、很慢或刚恢复。目标不是让所有请求都成功，而是在依赖故障时保持线程、连接、队列和数据库负载有上界，明确返回缓存结果、数据库结果、缺失或暂不可用。先完成C02有界执行器、C06 JDBC、C07前三节。本节组合真实Redis和MySQL，同时用T故障注入精确检验背压。

A覆盖真实暂停/进程中断/恢复、独占连接归还、真实数据库回源，以及可控饱和/取消；O要求指标和恢复拥塞分析；R读取客户端连接与线程池机制。调用端为了快速演示使用明确标注的固定回源fixture，真实数据库路径在IntegrationTest，不能混报。

## 概念、例子与ASCII

```text
请求 -> 有界Jedis池(2, 借用50ms, connect/read各150ms)
        | 命中 -> CACHE
        | 未命中/Redis异常
        v
     回源执行器(并发N, SynchronousQueue零等待队列)
        | 满 -> UNAVAILABLE + rejected计数
        | 接收 -> 有界Future等待 + 底层JDBC超时
                   | 有值 -> 尝试缓存 -> DATABASE
                   | 无值 -> MISSING
                   | 失败/超时 -> UNAVAILABLE

超时取消Future != 阻塞驱动已经停止
底层未结束仍占worker -> 新请求必须背压，不可“释放额度后继续加线程”
```

同一订单首次DATABASE，第二次CACHE；CLIENT PAUSE使Redis暂不能正常答复，客户端socket预算耗尽后走受限数据库；进程停止后继续受限回源；重启后新连接恢复共享缓存。没有声称每次请求必在某个精确毫秒完成，系统调度和网络重试也有成本。代码无自动请求重试，避免把一次调用放大成多轮数据库查询。

预算是分段的：借连接、建连、读响应、回源等待、回填各有边界，不等于一个贯穿全链路的绝对deadline。生产接口若要求总deadline，应在每段扣减剩余预算，取消时关闭底层资源。本课展示基础分段保护，独立迁移再做总预算。

## 编码步骤与调用验证

1. 运行`./gradlew :redis:07-resilience:run`，看fixture首次回源、命中、Redis停止后的DATABASE降级、重启后的恢复和指标。Usage会打印“回源是固定fixture”，不要作为数据库实测报告
2. 运行`./gradlew :redis:07-resilience:unitTest`。先读Cache/Origin接口、Result来源枚举、Metrics快照。修改`src/labs/Resilience.java`的`read`实现区，保留缓存失败计数，而不是把异常吞成命中
3. 在池中以try-with-resources借Jedis，池容量2、借用等待50ms、连接与socket各150ms。缓存miss或故障后向零等待队列的固定线程池提交回源，饱和立即返回UNAVAILABLE并记录rejected
4. 对已接收任务使用有界Future.get。超时cancel(true)、记录timedOut并返回UNAVAILABLE；收到中断恢复线程标记。底层任务可能不配合中断，不能伪造“任务已退出”
5. 可控单元测试让一个回源故意忽略中断，用latch保持运行。第二个请求被拒绝，第一个超时后activeOriginTasks仍为1；最后释放latch，close有界停止，不残留非daemon线程
6. 运行`./gradlew :redis:07-resilience:test`。真实MySQL建order_view并查询付款状态；Redis通过CLIENT PAUSE变慢，再真实SIGKILL不可用，然后重启。对业务来源与值、错误计数、最后activeConnections=0断言
7. 收集hits/originCalls/cacheErrors/rejected/timedOut，以及外部p50/p95/p99、命中率、数据库连接和恢复流量。不要平均多个p99，也不要把某台机器的毫秒数写成永远成立的测试门槛

## 标准解逐步解释与边界

[完整公开标准解](solution.md)。缓存是优化层，读取异常进入受限回源；回填失败不掩盖已经成功的数据库结果。Result把缺失与不可用分开，调用者可映射404和503，而不是都返回空对象。真实业务是否允许陈旧值、错误状态如何暴露，需要接口契约决定，本节不自动把陈旧订单当最新付款事实。

线程池无无界队列，也不用每超时一次就新开一个线程。工作线程真正退出之前仍占并发容量，所以取消无效不会无限扩张资源。close先shutdownNow再等待3秒；若底层任务无视取消，报告明确错误而不是静默挂住。这是资源生命周期保证的边界，不是凭Future状态证明远端SQL已停止。

每次读若缓存命中为一次GET，回源时最多再一次写缓存；没有自动retry。内存主要受线程数、连接数和应用请求体约束。JDBC设置connect/socket/query timeout并由try-with-resources释放；不同驱动的取消效果需真实环境验证。调用方不能把无界HTTP在途请求藏在本类之外然后宣称整体有界。

恢复时大量miss仍可压向数据库，单飞/抖动可进一步减少重复；负缓存是否加入本服务取决于新增订单可见性要求。熔断能减少持续坏Redis带来的延迟，但需要半开探测和状态测试，本节未实现完整breaker，不能在简历中声称已有。所有指标不使用用户ID做标签，避免高基数和信息泄漏。

本地缓存如果加进来，每个实例有独立生命周期；共享Redis删键不会自动清除本地副本。要么短TTL接受陈旧窗口，要么事件广播/版本校验，并解释消息漏发后的恢复。共享缓存恢复也不意味着每个本地副本已一致。

## 真实源码与机制路线

客户端固定Jedis **5.2.0** [Connection.java](https://github.com/redis/jedis/blob/v5.2.0/src/main/java/redis/clients/jedis/Connection.java)和[Pool.java](https://github.com/redis/jedis/blob/v5.2.0/src/main/java/redis/clients/jedis/util/Pool.java)，从连接建立、读响应和getResource追踪连接异常如何标记/归还。运行时依赖版本写在build.gradle，不混用其他客户端教程。

执行器机制固定[OpenJDK21+35 ThreadPoolExecutor.java](https://github.com/openjdk/jdk/blob/jdk-21%2B35/src/java.base/share/classes/java/util/concurrent/ThreadPoolExecutor.java)的`execute`、`addWorker`、`processWorkerExit`，对照零容量队列和AbortPolicy为何立即拒绝。Redis服务端暂停是测试注入，不代表所有真实网络故障；socket预算是在真实客户端读取路径验证。源码链接阅读与服务端动态测试状态分别记录。

## 面试问题、答案与递进追问

1. **Redis挂了直接查库是不是高可用？** 可能把故障转移成数据库雪崩。必须有回源并发/连接预算、拒绝策略及重要请求优先级，先估算退化流量
2. **加Future超时就能保证连接释放吗？** 不能。Future取消是Java层信号，底层socket/驱动需独立超时或关闭；测试故意保留忽略中断任务来揭示这点
3. **为什么无界队列危险？** 峰值请求会积压到超时之后仍执行，内存增长并形成恢复流量。零队列拒绝更早、更可解释，但牺牲部分短峰成功率
4. **回填失败要不要返回500？** 本读接口已有有效数据库结果，回填失败只影响后续命中，返回数据库结果并记录错误；若业务把缓存当事实库，契约会完全不同
5. **恢复后为什么还会出事故？** 缓存冷、批量重建和失败重试可能同步冲击数据库；限制恢复并发、分批预热/抖动，监控回源流量，不因PING恢复就立即取消所有保护
6. **命中率高就没有问题吗？** 不能，关键少数慢miss可能主导p99，热键偏斜和不同接口也会掩盖问题；按有意义低基数维度看延迟、错误、回源和容量

## 独立迁移与退出评阅

实现贯穿请求的单一deadline，缓存读、回源、回填都消耗剩余预算；补半开熔断一次只允许有限探针，并保持未结束回源的并发保护。测试中间取消、重复调用、Redis先慢后快、DB也失败四类组合。A要求业务状态和资源上界，O要求指标与故障矩阵，R要求真实连接/执行器路径。没有动态Docker证据时，纯测试只能算T保护逻辑通过，不算生产故障演练完成。
