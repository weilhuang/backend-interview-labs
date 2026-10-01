# 08 高并发库存、容量与故障答辩

对应目录 C10-08。Java 21主线，本节可独立选择Gradle模块；依赖版本、完整源码与发布状态见课程首页。所有调用方、测试、数据定义和标准解直接可见。

## 企业场景

把真实gRPC、Dubbo与同一持久化幂等库存连接起来。压测30个不同订单争抢10件库存，系统只成功10次；重复已成功订单不能再次扣减。设计评审还需要回答热点、分片、ID、异地、降级与回滚。

## 概念逐层建立

- 稳态近似Little定律：在途数≈到达率×平均服务时间；增加安全余量不是把平均值变成尾延迟保证
- 无队列准入让过载尽早显式失败。虚拟线程降低线程成本，不扩大数据库连接、锁和远端额度
- 单机额度乘以实例数才是集群上限，扩容前需按数据库共享池预算重新分配；超时和重试额外消耗资源
- 唯一ID位布局只是编码。工作节点号唯一、时钟回退、每毫秒序列耗尽和重启状态仍需要协议与持久化约束
- 按订单ID分片利于均匀写与点查，按用户/商家分片利于局部事务；热点sku库存可能仍集中，不能靠随机ID自动消除
- 库存不超卖是主库条件写不变量；列表可以允许陈旧，结算确认必须回主库。异地多写需要另定义库存额度分配或共识策略
- 回滚兼容不仅是代码：proto、幂等记录、事件schema、数据库字段和已提交外部效果都要能被旧版理解

## ASCII机制图

```text
30个客户端 -> gRPC输入校验 -> Admission(最多8在途)
                                      |
                              数据库幂等领取/重放
                                      |
                     UPDATE inventory ... available>=quantity
                                      |
                           库存+操作结果同事务提交

10件库存 -> 成功10个不同键 + 其余稳定拒绝
同键重放 -> 原操作结果，不再扣减
```

## 实际操作与逐步编码

1. 计算1000请求/秒、平均80毫秒、1.5倍余量所需120在途；如果数据库分给本服务80连接，先限制额度并测吞吐
2. 实现Admission.execute，使用tryAcquire立即拒绝、finally释放；用屏障验证容量1时第二个请求不能进入
3. 实现IdLayout.compose并验证41/10/12位边界，解释相同节点号/时间/序列会碰撞，函数本身不分配节点租约
4. 运行网络+H2 SQL烟测，同键两次RPC只扣一次。明确这不是MySQL锁与恢复验证
5. 执行真实MySQL+gRPC集成，30个订单最多8并发争抢10件，断言成功10次、库存0、完成记录10条；再执行Dubbo+MySQL同键回放与参数冲突
6. 重放任一成功键，结果是最初那次响应，库存仍为0；关闭服务后确认资源退出
7. 完成故障矩阵与容量设计答辩：依赖宕机、缓存不可用、消息积压、注册中心失联、热点/扩容/回滚，逐项给证据和局限

以下命令用于源码仓库/公开源码包；Academy官方ZIP内用Check/Run或Gradle工具窗口执行同名任务。官方导出可能剔除Wrapper脚本/JAR，不能假设导入目录能直接运行./gradlew。独立服务课需同源shared/versions.env快照，缺失时不能视为发行完成。

本节单元检查：`./gradlew :08-capacity:test`；完整调用端：`./gradlew :08-capacity:run`。含数据库/消息服务的单元另执行 `./gradlew :08-capacity:integrationTest`，Docker不可用应明确失败，不能跳过后当作通过。每次修改先跑对应方法测试，再跑全模块回归。

## 正确性合同与保证边界

端到端库存保证只覆盖一个MySQL主库内的库存与幂等结果；没有多主跨地域库存保证。准入是每进程上限，不自动提供公平性。SQL驱动与查询有独立超时，RPC取消不承诺立即中止数据库；未知结果仍按业务键恢复。集成测试规模用于验证性质，不是性能基准或生产容量证明。

## 固定版本源码阅读

- [grpc/grpc-java v1.71.0：ClientCallImpl.java](https://github.com/grpc/grpc-java/blob/865c4432569dfdf738b3cf07bcdb6d6e3285f761/core/src/main/java/io/grpc/internal/ClientCallImpl.java)
- [grpc/grpc-java v1.71.0：RetriableStream.java](https://github.com/grpc/grpc-java/blob/865c4432569dfdf738b3cf07bcdb6d6e3285f761/core/src/main/java/io/grpc/internal/RetriableStream.java)
- [grpc/grpc-java v1.71.0：ClientCalls.java](https://github.com/grpc/grpc-java/blob/865c4432569dfdf738b3cf07bcdb6d6e3285f761/stub/src/main/java/io/grpc/stub/ClientCalls.java)
- [grpc/grpc-java v1.71.0：ServerCalls.java](https://github.com/grpc/grpc-java/blob/865c4432569dfdf738b3cf07bcdb6d6e3285f761/stub/src/main/java/io/grpc/stub/ServerCalls.java)
- [mysql/mysql-connector-j 9.2.0：MysqlXAConnection.java](https://github.com/mysql/mysql-connector-j/blob/a3909bfeb62d5a517ab444bb88ba7ecf26100297/src/main/user-impl/java/com/mysql/cj/jdbc/MysqlXAConnection.java)

阅读任务：先在本节测试找到症状，再记录入口、关键状态、分支条件和返回/清理路径。每个结论附输入、版本、符号与反例。详细入口、关键状态、分支条件和实验证据对照见课程 docs/源码路线.md。源码字节哈希与标签解析结果在课程作者验证记录中公开；没有截图不伪称做过IDE断点。

## 公开完整标准解

完整Java文件位于本节 `solutions/`，与本节标准实现逐字同步，依赖接口、调用方和测试也在本节可见。下面列出全部编码区，便于先独立完成再核对；不需要解锁或另取私有分支。

### src/labs/distributed/capacity/Admission.java 的练习实现

```java
    if (!permits.tryAcquire()) throw new RejectedExecutionException("容量已满，请按预算退避");
    int current = active.incrementAndGet();
    peak.accumulateAndGet(current, Math::max);
    try {
      return work.call();
    } finally {
      active.decrementAndGet();
      permits.release();
    }
```
### src/labs/distributed/capacity/Admission.java 的练习实现

```java
    double demand = requestsPerSecond * latencySeconds * headroom;
    if (!Double.isFinite(demand)
        || requestsPerSecond <= 0
        || latencySeconds <= 0
        || headroom < 1
        || demand > Integer.MAX_VALUE) throw new IllegalArgumentException("容量参数非法或溢出");
    return Math.max(1, (int) Math.ceil(demand));
```
### src/labs/distributed/capacity/IdLayout.java 的练习实现

```java
    if (elapsedMillis < 0
        || elapsedMillis >= (1L << 41)
        || worker < 0
        || worker >= 1024
        || sequence < 0
        || sequence >= 4096) throw new IllegalArgumentException("ID位字段越界");
    return (elapsedMillis << 22) | ((long) worker << 12) | sequence;
```

## 标准解机制、复杂度与替代取舍

DatabaseInventory把C10-05存储注入C10-02真实网络服务，DubboDatabaseInventory把完全相同业务合同适配到C10-03真实远程服务，整个业务调用受同一Admission保护。原子条件写防止库存变负，稳定保存不足结果防止同key以后意外成功。返回RESOURCE_EXHAUSTED表示入口容量拒绝，FAILED_PRECONDITION表示业务条件不满足，UNAVAILABLE表示暂时失败或未知结果需恢复。

## 面试机制、边界与深入追问

- 问：如何证明不超卖？答：主库事务内条件更新只在available>=quantity时扣减，测试并发最后守恒；多主/跨分片需另证明
- 问：容量估算为何不能直接当压测结果？答：服务时间分布、锁竞争、连接建连、GC和热点会改变尾延迟，需要受控负载与监控复核
- 问：雪花ID是否天然全局唯一？答：位布局之外还需唯一worker租约、时钟回退策略、序列限额与重启状态，单个compose函数不保证这些
- 问：缓存挂了能否全部回源？答：直接全量回源可能打穿数据库，应准入、合并请求、分级降级并保护关键结算路径
- 问：如何扩展到异地？答：先选一致性目标与故障下可用性，可预分库存额度或单主/共识；代价是额度闲置、跨区延迟或分区时拒绝
- 迁移答辩：把单sku扩展为两sku订单，画锁顺序/死锁重试、跨分片事务与补偿路径；比较两种方案而非宣称唯一正确架构

## 三阶提示与独立验收

1. 基础提示：先列正常、边界、失败后的持久状态，找到测试的业务断言，不先复制实现
2. 机制提示：把每次外部提交、响应、日志落盘、资源归还画成独立事件，检查任意相邻事件间崩溃的后果
3. 深入提示：找真正执行原子操作的数据库/框架分支，确认幂等、锁、时间与持久化前提没有被内存模型替代

独立完成一个迁移题，补失败测试，解释一份错误实现被哪条断言拒绝，再做5分钟机制答辩。看过标准答案只记录“已阅读”，不能记录“独立掌握”。实际执行通过、未执行和已知边界见课程根中文阶段报告。
