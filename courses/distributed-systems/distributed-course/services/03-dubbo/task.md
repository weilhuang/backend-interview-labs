# 03 Dubbo调用链、发现与治理

对应目录 C10-03。Java 21主线，本节可独立选择Gradle模块；依赖版本、完整源码与发布状态见课程首页。所有调用方、测试、数据定义和标准解直接可见。

## 企业场景

同一库存契约在Java服务间使用Dubbo。两台提供者通过真实ZooKeeper发布地址，消费者轮询分配请求；其中一台退出后，不把注册发现变化误当作调用立即无错误。

## 概念逐层建立

- 注册中心负责提供者地址及变化通知；业务请求由消费者直接通过Dubbo协议到提供者，不经注册中心转发
- `ReferenceConfig`构建代理，cluster/router/loadbalance选择Invoker，协议层完成序列化与远程传输，filter建立横切处理
- 本课显式`setScope("remote")`，防止同一JVM部署误走本地调用，网络结果包含提供者ID和附件
- 本课使用failfast+应用层只读有界重试。写reserve没有自动重试；本节fixture提供计数副作用暴露风险，C10-08通过可注入Inventory实现接入MySQL幂等合同
- provider filter校验trace和remaining budget，消费者每次尝试重新计算同一个总截止的剩余时间，并清理附件
- 真实嵌入式ZooKeeper仅在测试中运行，随机回环端口。生产集群多数派、ACL、会话过期与跨地域部署不是一个TestingServer可证明的能力

## ASCII机制图

```text
提供者A --注册--> ZooKeeper <--订阅-- 消费者代理
提供者B --注册-->     |                  |
                     +--地址通知------> Directory
                                         |
                        cluster -> loadbalance -> Invoker
                                         |
                        TCP Dubbo -> provider filter -> Inventory
```

## 实际操作与逐步编码

1. 运行 `:03-dubbo:run`：看到真实Dubbo协议结果，读取接口Inventory和两个完整调用类
2. 实现 `BudgetFilter.invoke`，拒绝非法追踪和0/过大预算；先理解过滤器何时执行，再修改业务方法
3. 实现 `Client.quote` 的单个总预算循环，只对非业务RpcException尝试重试；每次finally清理client attachment
4. 运行DubboTest确认参数拒绝与只写一次，再停止提供者，断言有限时间内结束而非无限等待
5. 运行DiscoveryTest：真实ZooKeeper启动，两提供者注册地址；12次调用应覆盖两个提供者
6. 停止一个提供者，等待注册通知与调用恢复，在有界8秒观察窗口内确认另一个可用。记下短暂失败是发现延迟还是业务异常
7. 源码断点从ReferenceConfig.get走到FailoverClusterInvoker.doInvoke，比较本实验failfast为什么没有隐式多次写入

以下命令用于源码仓库/公开源码包；Academy官方ZIP内用Check/Run或Gradle工具窗口执行同名任务。官方导出可能剔除Wrapper脚本/JAR，不能假设导入目录能直接运行./gradlew。独立服务课需同源shared/versions.env快照，缺失时不能视为发行完成。

本节单元检查：`./gradlew :03-dubbo:test`；完整调用端：`./gradlew :03-dubbo:run`。含数据库/消息服务的单元另执行 `./gradlew :03-dubbo:integrationTest`，Docker不可用应明确失败，不能跳过后当作通过。每次修改先跑对应方法测试，再跑全模块回归。

## 正确性合同与保证边界

只读quote最大3次、总预算最多5秒。每次写reserve只调用一次，未知结果后不盲目重发。注册发现测试的单节点ZooKeeper与本机端口只证明协议集成，不代表生产HA。`budget-ms`是收到时的相对上限，不能宣称天然解决任意时钟/传输延迟；调用方总预算与Dubbo超时共同限制等待。

## 固定版本源码阅读

- [apache/dubbo dubbo-3.3.6：FailoverClusterInvoker.java](https://github.com/apache/dubbo/blob/f1585880bee4ca7776f44380c47c994217721ffe/dubbo-cluster/src/main/java/org/apache/dubbo/rpc/cluster/support/FailoverClusterInvoker.java)
- [apache/dubbo dubbo-3.3.6：ReferenceConfig.java](https://github.com/apache/dubbo/blob/f1585880bee4ca7776f44380c47c994217721ffe/dubbo-config/dubbo-config-api/src/main/java/org/apache/dubbo/config/ReferenceConfig.java)
- [apache/dubbo dubbo-3.3.6：ContextFilter.java](https://github.com/apache/dubbo/blob/f1585880bee4ca7776f44380c47c994217721ffe/dubbo-rpc/dubbo-rpc-api/src/main/java/org/apache/dubbo/rpc/filter/ContextFilter.java)
- [apache/dubbo dubbo-3.3.6：ZookeeperRegistry.java](https://github.com/apache/dubbo/blob/f1585880bee4ca7776f44380c47c994217721ffe/dubbo-registry/dubbo-registry-zookeeper/src/main/java/org/apache/dubbo/registry/zookeeper/ZookeeperRegistry.java)

阅读任务：先在本节测试找到症状，再记录入口、关键状态、分支条件和返回/清理路径。每个结论附输入、版本、符号与反例。详细入口、关键状态、分支条件和实验证据对照见课程 docs/源码路线.md。源码字节哈希与标签解析结果在课程作者验证记录中公开；没有截图不伪称做过IDE断点。

## 公开完整标准解

完整Java文件位于本节 `solutions/`，与本节标准实现逐字同步，依赖接口、调用方和测试也在本节可见。下面列出全部编码区，便于先独立完成再核对；不需要解锁或另取私有分支。

### src/labs/distributed/dubbo/BudgetFilter.java 的练习实现

```java
    String trace = invocation.getAttachment("trace-id");
    String budget = invocation.getAttachment("budget-ms");
    if (trace == null || !trace.matches("[a-zA-Z0-9_-]{1,64}")) {
      throw new RpcException(RpcException.BIZ_EXCEPTION, "追踪标识缺失或非法");
    }
    long millis;
    try {
      millis = Long.parseLong(budget);
    } catch (RuntimeException failure) {
      throw new RpcException(RpcException.BIZ_EXCEPTION, "预算格式非法");
    }
    if (millis < 1 || millis > 5000) {
      throw new RpcException(RpcException.BIZ_EXCEPTION, "预算超出允许范围");
    }
    return invoker.invoke(invocation);
```
### src/labs/distributed/dubbo/Lab.java 的练习实现

```java
      for (int attempt = 0; attempt < maxAttempts; attempt++) {
        long remaining = TimeUnit.NANOSECONDS.toMillis(end - System.nanoTime());
        if (remaining <= 0) break;
        try {
          attach(trace, remaining);
          return proxy.quote(sku);
        } catch (RpcException failure) {
          if (failure.isBiz()) throw failure;
          last = failure;
        } finally {
          RpcContext.removeClientAttachment();
        }
      }
      throw new RpcException(RpcException.TIMEOUT_EXCEPTION, "只读调用重试预算耗尽", last);
```

## 标准解机制、复杂度与替代取舍

provider使用ServiceConfig导出实际网络协议，consumer限定remote scope。外层重试重新计算remaining并传入RPC附件，永久业务错误直接抛出。调用完成后移除附件，避免复用工作线程串联不同请求。发现和故障测试使用真实注册服务，但其恢复时长不用于任何生产SLO承诺。

## 面试机制、边界与深入追问

- 问：注册中心宕机后业务一定不可用？答：已有地址缓存可继续调用仍健康提供者，新发现/变更传播受影响；必须区分控制面与数据面
- 问：retries=2代表几次尝试？答：通常是初次加两次重试，必须按固定源码确认；多层3次可放大成3的层数次
- 问：为什么写请求禁用框架重试？答：没有持久化幂等合同的超时写可能已经完成；框架无法替业务判定安全
- 问：轮询会平均负载吗？答：只均衡选择次数，处理成本、连接/权重、慢节点和热点可使资源负载不均
- 问：filter与业务事务有什么不同？答：filter管理调用上下文、校验和横切逻辑，不能自动为远端多个数据库建立同一事务
- 迁移：新增一个明确幂等的查询方法，并给它单独预算；写出只读与写方法不同重试策略的证据

## 三阶提示与独立验收

1. 基础提示：先列正常、边界、失败后的持久状态，找到测试的业务断言，不先复制实现
2. 机制提示：把每次外部提交、响应、日志落盘、资源归还画成独立事件，检查任意相邻事件间崩溃的后果
3. 深入提示：找真正执行原子操作的数据库/框架分支，确认幂等、锁、时间与持久化前提没有被内存模型替代

独立完成一个迁移题，补失败测试，解释一份错误实现被哪条断言拒绝，再做5分钟机制答辩。看过标准答案只记录“已阅读”，不能记录“独立掌握”。实际执行通过、未执行和已知边界见课程根中文阶段报告。
