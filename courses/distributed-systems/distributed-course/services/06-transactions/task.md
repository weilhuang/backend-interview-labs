# 06 XA、TCC与Saga真实恢复

对应目录 C10-06。Java 21主线，本节可独立选择Gradle模块；依赖版本、完整源码与发布状态见课程首页。所有调用方、测试、数据定义和标准解直接可见。

## 企业场景

库存与积分支付由不同数据库负责。数据库内事务不能自动覆盖两个服务。分别实现XA准备/恢复、TCC预留/确认/取消，以及可重放的Saga日志，比较资源锁、业务中间态与恢复责任。

## 概念逐层建立

- 2PC分为准备与决策两个阶段，参与者PREPARED后可能持锁等待；协调者必须先持久化决策再通知提交
- 本课用真实MySQL XAResource、两个MySQL实例与fsync决策文件，重建连接后XA RECOVER恢复；不是Java布尔变量模拟2PC
- TCC把业务资源显式预留，Try/Confirm/Cancel都需幂等；空回滚留下墓碑，晚到Try被拒绝，防止悬挂
- Saga每步是独立本地事务，补偿是另一次业务行为。中间态可见，补偿可能失败，也不能撤回已发短信或物理发货
- 本课Saga记录步骤，参与者独立数据库提交；丢失协调检查点后重试同一参与者键，避免二次扣款
- Seata/商业事务协调器适配不在此实现内：没有声称完成集群协调、日志复制、启发式决策、管理控制台或自动灾备

## ASCII机制图

```text
XA：资源A PREPARE --+
                    +-> 协调日志 COMMIT + fsync -> A/B COMMIT
    资源B PREPARE --+          |
                              崩溃后按日志恢复；无决策则回滚

TCC：NEW -> RESERVED -> CONFIRMED
       \       |
        \      +-----> CANCELLED（重复取消不再加库存）
         +空回滚-----> CANCELLED（墓碑阻止迟到Try）

Saga：STARTED -> RESERVED -> COMPLETED
          \         \失败
           +------> COMPENSATING -> CANCELLED
```

## 实际操作与逐步编码

1. 先运行TCC SQL合同测试，画available+reserved+sold守恒式；编码reserve与finish
2. 验证重复Confirm/Cancel、同键参数冲突、Cancel先到、Try晚到、Confirm之后不能用Cancel反向撤销
3. 编写Saga.step的状态推进。每个参与者成功后、协调日志更新前注入崩溃，重建Saga对象并继续
4. 在退款后、库存释放前再次注入故障，重试补偿应最终归还资源且不重复退款
5. 阅读XaTransfer中真实XAConnection与Xid，编码两个prepare、落盘决策、两个commit的严格顺序
6. Docker中执行两个MySQL资源：仅PREPARED没有日志时恢复回滚；已有COMMIT日志后重启两个数据库，fresh inspect取得实际新端口，显式重建Database/XA恢复器，恢复提交后余额70/130且重复恢复返回0
7. 记录PREPARED期间哪些资源仍可能持锁、人工恢复需要哪些证据。不得为了消除阻塞擅自对未知事务执行相反决策

以下命令用于源码仓库/公开源码包；Academy官方ZIP内用Check/Run或Gradle工具窗口执行同名任务。官方导出可能剔除Wrapper脚本/JAR，不能假设导入目录能直接运行./gradlew。独立服务课需同源shared/versions.env快照，缺失时不能视为发行完成。

本节完整判题：`./gradlew :06-transactions:test`，同时执行合同测试与真实服务测试；Academy Check 使用此默认入口，需要可用Docker。只完成纯合同部分、XA/发布/缓存编码区仍为TODO时不得判为完成；缺Docker、镜像拉取失败或服务启动异常也应失败，不能当作错误答案被正确拒绝。局部快测可显式执行 `./gradlew :06-transactions:unitTest`，绿色仅代表不依赖Docker的合同，不代表本节完成。`./gradlew :06-transactions:integrationTest` 保留为单独真实服务回归；完整调用端为 `./gradlew :06-transactions:run`。方法/类过滤仅用于定位问题，完成判定必须不加过滤地执行完整模块test。

## 正确性合同与保证边界

XA是单协调者、每笔事务独立日志文件的受控实验。日志文件创建使用CREATE_NEW，禁止覆盖原决策；不能丢失/篡改日志后仍声称安全恢复。MySQL8.4默认支持prepare后detach，恢复账号需要XA_RECOVER_ADMIN。Docker重启可能重新绑定随机宿主端口；restartAndAwait返回新的不可变Database，必须用它重建协调器。此为测试夹具主动发现，不承诺普通JDBC连接池会自动发现Docker新端口。Saga为了简单串行化在一步内持有协调行锁跨参与者调用，故需有界超时并承认锁开销。正常完成表示“库存已预留、积分已扣”，发货确认属于后续业务。

## 固定版本源码阅读

- [mysql/mysql-connector-j 9.2.0：MysqlXAConnection.java](https://github.com/mysql/mysql-connector-j/blob/a3909bfeb62d5a517ab444bb88ba7ecf26100297/src/main/user-impl/java/com/mysql/cj/jdbc/MysqlXAConnection.java)
- [MySQL8.4 XA状态与detach](https://dev.mysql.com/doc/refman/8.4/en/xa-states.html)
- [MySQL8.4 XA限制](https://dev.mysql.com/doc/refman/8.4/en/xa-restrictions.html)

阅读任务：先在本节测试找到症状，再记录入口、关键状态、分支条件和返回/清理路径。每个结论附输入、版本、符号与反例。详细入口、关键状态、分支条件和实验证据对照见课程 docs/源码路线.md。源码字节哈希与标签解析结果在课程作者验证记录中公开；没有截图不伪称做过IDE断点。

## 公开完整标准解

完整Java文件位于本节 `solutions/`，与本节标准实现逐字同步，依赖接口、调用方和测试也在本节可见。下面列出全部编码区，便于先独立完成再核对；不需要解锁或另取私有分支。

### src/labs/distributed/transactions/Saga.java 的练习实现

```java
            String next =
                switch (state) {
                  case "STARTED" -> {
                    boolean reserved = inventory.reserve(id, "book", rows.getInt("quantity"));
                    failurePoint.after("库存提交后日志前");
                    yield reserved ? "RESERVED" : "COMPENSATING";
                  }
                  case "RESERVED" -> {
                    boolean charged = payment.charge(id, rows.getInt("amount"));
                    failurePoint.after("支付提交后日志前");
                    yield charged ? "COMPLETED" : "COMPENSATING";
                  }
                  case "COMPENSATING" -> {
                    payment.refund(id);
                    failurePoint.after("退款后库存释放前");
                    if (!inventory.cancel(id))
                      throw new IllegalStateException("库存补偿未完成，必须继续重试或人工核对");
                    yield "CANCELLED";
                  }
                  default -> state;
                };
            Database.update(connection, "UPDATE saga_log SET state=? WHERE saga_id=?", next, id);
            return next;
```
### src/labs/distributed/transactions/TccInventory.java 的练习实现

```java
            if (state.equals("CANCELLED")) return false;
            if (!sku.equals(rows.getString("sku")) || quantity != rows.getInt("quantity")) {
              throw new IllegalArgumentException("分支键参数冲突");
            }
            if (state.equals("RESERVED") || state.equals("CONFIRMED")) return true;
            if (Database.update(
                    connection,
                    "UPDATE tcc_stock SET available=available-?, reserved=reserved+? WHERE sku=?"
                        + " AND available>=?",
                    quantity,
                    quantity,
                    sku,
                    quantity)
                == 0) return false;
            Database.update(
                connection, "UPDATE tcc_branch SET state='RESERVED' WHERE branch_id=?", id);
            return true;
```
### src/labs/distributed/transactions/TccInventory.java 的练习实现

```java
            if (confirm && state.equals("CONFIRMED")) return true;
            if (!confirm && state.equals("CANCELLED")) return true;
            if (!confirm && state.equals("NEW")) {
              Database.update(
                  connection, "UPDATE tcc_branch SET state='CANCELLED' WHERE branch_id=?", id);
              return true;
            }
            if (!state.equals("RESERVED")) return false;
            String sql =
                confirm
                    ? "UPDATE tcc_stock SET reserved=reserved-?, sold=sold+? WHERE sku=? AND"
                        + " reserved>=?"
                    : "UPDATE tcc_stock SET reserved=reserved-?, available=available+? WHERE sku=?"
                        + " AND reserved>=?";
            if (Database.update(connection, sql, quantity, quantity, sku, quantity) != 1) {
              throw new IllegalStateException("库存守恒被破坏，禁止静默补偿");
            }
            Database.update(
                connection,
                "UPDATE tcc_branch SET state=? WHERE branch_id=?",
                confirm ? "CONFIRMED" : "CANCELLED",
                id);
            return true;
```
### src/labs/distributed/transactions/XaTransfer.java 的练习实现

```java
        if (ra.prepare(xa) != XAResource.XA_OK || rb.prepare(xb) != XAResource.XA_OK) {
          throw new IllegalStateException("预期两个写分支都进入PREPARED");
        }
        prepared = true;
        if (stopAfterPrepare) return;
        decision(id);
        if (stopAfterDecision) return;
        ra.commit(xa, false);
        rb.commit(xb, false);
```

## 标准解机制、复杂度与替代取舍

TCC先用唯一分支行建立串行化点，再在同一个事务内改变库存与分支状态；Cancel不存在分支时插入墓碑。Saga每步的远端效果不和协调日志假装原子，通过参与者幂等键恢复“远端成功、日志未写”窗口。XA先让两个分支准备，只有持久化COMMIT以后才提交；恢复按格式ID和全局ID筛选，不触碰别的事务。

## 面试机制、边界与深入追问

- 问：2PC为什么会阻塞？答：参与者准备后不能独立知道全局决策，协调日志不可用时可能等待并持有资源
- 问：TCC的空回滚和悬挂是什么？答：Cancel早于Try到达需留墓碑；随后迟到Try不能重新预留，否则取消后的资源又被占用
- 问：Saga补偿等于数据库rollback吗？答：不是，它是新的业务事务，中间状态可能被观察且外部副作用未必可逆
- 问：补偿失败是否可把Saga直接标为CANCELLED？答：不能，必须持久化待补偿状态、重试预算与人工处理入口
- 问：XA恢复为何要读日志而不是看两个余额猜？答：余额包含其他并发交易，不能推断本事务决策；启发式回滚会破坏原子性
- 迁移：增加第三个可失败参与者，写清逆序补偿、重复步骤、支付成功但通知丢失的恢复路径，并指出哪些效果不能补偿

## 三阶提示与独立验收

1. 基础提示：先列正常、边界、失败后的持久状态，找到测试的业务断言，不先复制实现
2. 机制提示：把每次外部提交、响应、日志落盘、资源归还画成独立事件，检查任意相邻事件间崩溃的后果
3. 深入提示：找真正执行原子操作的数据库/框架分支，确认幂等、锁、时间与持久化前提没有被内存模型替代

独立完成一个迁移题，补失败测试，解释一份错误实现被哪条断言拒绝，再做5分钟机制答辩。看过标准答案只记录“已阅读”，不能记录“独立掌握”。实际执行通过、未执行和已知边界见课程根中文阶段报告。
