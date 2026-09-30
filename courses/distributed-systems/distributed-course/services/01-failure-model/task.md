# 01 故障模型、网络与未知结果

对应目录 C10-01。Java 21主线，本节可独立选择Gradle模块；依赖版本、完整源码与发布状态见课程首页。所有调用方、测试、数据定义和标准解直接可见。

## 企业场景

电商调用方在200毫秒内未拿到库存响应。客服问“是不是没有扣库存”。同一超时现象既可能对应请求没有到达，也可能对应事务已经提交而响应丢失。先用可控事件模型区分业务事实与调用方知识，再到后两节观察真实网络。

## 概念逐层建立

- 故障模型中的进程崩溃、消息丢失、延迟、重复、乱序分别改变什么，不能用一个“异常”代替
- TCP提供单连接有序字节流，不提供消息边界或业务恰好执行一次；HTTP需要自己的请求/响应与幂等合同
- HTTP/2在一条TCP连接上多路复用流，连接级故障仍会影响多条流；应用流控和TCP拥塞控制不是同一层
- DNS缓存和连接池会延长旧地址的影响。建连、取连接、写、读、总deadline需要分开预算
- CAP中的一致性通常指线性一致性，可用性有严格“非故障节点收到的请求最终有响应”定义。发生分区时，跨分区维持线性一致性可能拒绝/等待请求；不能把CAP说成平时任选两个
- PACELC补充无分区时复制延迟与一致性取舍。这里没有实现共识协议，事件模拟不能证明CAP或任何数据库的全局性质

## ASCII机制图

```text
调用方                  网络                 服务端
  SEND -------------------------------> 本地事务COMMIT
   |                       X <----------- REPLY丢失
  TIMEOUT
   v
 UNKNOWN（可能提交，也可能没到达）
   |
 同一业务键查询/恢复，而不是把未知改成失败
```

## 实际操作与逐步编码

1. 运行 `:01-failure-model:run`，写出时间点0、10、20、30毫秒的调用方状态
2. 在 `Lab.simulate` 实现状态转换。运行 `LabTest.提交成功但响应丢失仍是未知` 与延迟响应测试
3. 构造同样的UNKNOWN但提交次数分别为0和1的事件序列，解释为何调用方无法从超时区分
4. 实现 `downstreamBudget`：从剩余100毫秒保留30毫秒，下游上限80毫秒，得到70毫秒；不足时返回0
5. 运行全部测试，再自己加一个重复发送导致二次提交的反例；不要修改合同强行让未知等于失败

以下命令用于源码仓库/公开源码包；Academy官方ZIP内用Check/Run或Gradle工具窗口执行同名任务。官方导出可能剔除Wrapper脚本/JAR，不能假设导入目录能直接运行./gradlew。独立服务课需同源shared/versions.env快照，缺失时不能视为发行完成。

本节单元检查：`./gradlew :01-failure-model:test`；完整调用端：`./gradlew :01-failure-model:run`。含数据库/消息服务的单元另执行 `./gradlew :01-failure-model:integrationTest`，Docker不可用应明确失败，不能跳过后当作通过。每次修改先跑对应方法测试，再跑全模块回归。

## 正确性合同与保证边界

时间为非负逻辑毫秒，同一时刻按输入顺序。晚到响应不复活已经结束的调用。COMMIT计数是故意没有幂等保护的模型。模型没有模拟TCP重传、持久化、跨线程竞态；网络事实由C10-02/03测试。

## 固定版本源码阅读

- [grpc/grpc-java v1.71.0：ClientCallImpl.java](https://github.com/grpc/grpc-java/blob/865c4432569dfdf738b3cf07bcdb6d6e3285f761/core/src/main/java/io/grpc/internal/ClientCallImpl.java)
- [grpc/grpc-java v1.71.0：RetriableStream.java](https://github.com/grpc/grpc-java/blob/865c4432569dfdf738b3cf07bcdb6d6e3285f761/core/src/main/java/io/grpc/internal/RetriableStream.java)
- [grpc/grpc-java v1.71.0：ClientCalls.java](https://github.com/grpc/grpc-java/blob/865c4432569dfdf738b3cf07bcdb6d6e3285f761/stub/src/main/java/io/grpc/stub/ClientCalls.java)
- [grpc/grpc-java v1.71.0：ServerCalls.java](https://github.com/grpc/grpc-java/blob/865c4432569dfdf738b3cf07bcdb6d6e3285f761/stub/src/main/java/io/grpc/stub/ServerCalls.java)
- [TCP RFC9293](https://www.rfc-editor.org/rfc/rfc9293.html)
- [HTTP/2 RFC9113](https://www.rfc-editor.org/rfc/rfc9113.html)
- [PACELC原论文](https://www.cs.umd.edu/~abadi/papers/abadi-pacelc.pdf)

阅读任务：先在本节测试找到症状，再记录入口、关键状态、分支条件和返回/清理路径。每个结论附输入、版本、符号与反例。详细入口、关键状态、分支条件和实验证据对照见课程 docs/源码路线.md。源码字节哈希与标签解析结果在课程作者验证记录中公开；没有截图不伪称做过IDE断点。

## 公开完整标准解

完整Java文件位于本节 `solutions/`，与本节标准实现逐字同步，依赖接口、调用方和测试也在本节可见。下面列出全部编码区，便于先独立完成再核对；不需要解锁或另取私有分支。

### src/labs/distributed/Lab.java 的练习实现

```java
      switch (event) {
        case SEND -> state = Knowledge.IN_FLIGHT;
        case COMMIT -> committed++;
        case REPLY -> {
          if (state == Knowledge.IN_FLIGHT) {
            state = Knowledge.SUCCEEDED;
          }
        }
        case TIMEOUT, DISCONNECT -> {
          if (state == Knowledge.IN_FLIGHT) {
            state = Knowledge.UNKNOWN;
          }
        }
      }
```
### src/labs/distributed/Lab.java 的练习实现

```java
    if (remaining.isNegative() || localReserve.isNegative() || cap.isNegative()) {
      throw new IllegalArgumentException("预算不能为负数");
    }
    Duration available = remaining.minus(localReserve);
    if (available.isZero() || available.isNegative()) {
      return Duration.ZERO;
    }
    return available.compareTo(cap) < 0 ? available : cap;
```

## 标准解机制、复杂度与替代取舍

模拟器保留知识状态和提交次数两个维度，避免把客户端超时解释成远端回滚。复杂度为排序O(n log n)、轨迹O(n)。预算用Duration的减法和比较，而不把各跳timeout直接相加。另一种正确实现可先检查remaining<=reserve，再返回min(remaining-reserve, cap)。

## 面试机制、边界与深入追问

- 问：超时为何不能当作失败？答：提交与响应是两个不同事件。追问：如果只有读请求呢？读本身无写副作用，但结果仍可能过期，重试也消耗预算
- 问：有TCP为何还会重复订单？答：应用在另一次调用中重发业务请求；TCP序号只对连接字节有效。边界：断连后重建连接不共享业务去重状态
- 问：连接池越大越好吗？答：过大可把排队移到数据库，增加尾延迟；用到达率、服务时间和下游容量定额度
- 问：CAP与数据库事务ACID中的C一样吗？答：不是，前者讨论副本读写一致性，后者约束事务前后的业务/数据不变量
- 迁移：增加“客户端取消但服务端忽略取消”的事件，证明取消和回滚也不是同义词

## 三阶提示与独立验收

1. 基础提示：先列正常、边界、失败后的持久状态，找到测试的业务断言，不先复制实现
2. 机制提示：把每次外部提交、响应、日志落盘、资源归还画成独立事件，检查任意相邻事件间崩溃的后果
3. 深入提示：找真正执行原子操作的数据库/框架分支，确认幂等、锁、时间与持久化前提没有被内存模型替代

独立完成一个迁移题，补失败测试，解释一份错误实现被哪条断言拒绝，再做5分钟机制答辩。看过标准答案只记录“已阅读”，不能记录“独立掌握”。实际执行通过、未执行和已知边界见课程根中文阶段报告。
