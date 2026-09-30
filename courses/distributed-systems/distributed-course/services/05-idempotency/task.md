# 05 持久化幂等、租约与重试预算

对应目录 C10-05。Java 21主线，本节可独立选择Gradle模块；依赖版本、完整源码与发布状态见课程首页。所有调用方、测试、数据定义和标准解直接可见。

## 企业场景

两个应用实例同时收到相同订单键。一个实例领取后崩溃，另一个稍后接管；旧实例又恢复。正确实现既不能二次扣库存，也不能让旧持有者凭已过期租约提交。

## 概念逐层建立

- 键作用域包含租户、业务类型与业务ID，参数指纹与键一起检查；同键不同参数应冲突而不是返回旧成功
- PENDING、COMPLETED与不存在分别代表处理中或可领取占位、已知终态、尚无法确认，不存在不等价“从未执行”
- 登记是独立自动提交：成功后即绑定原参数，即使随后崩溃/业务回滚也不删除。owner为空、generation=0、lease_until=0的占位可立即重新领取，不是永久处理中
- 租约只是时间许可，代次/owner是拒绝旧执行者的栅栏；以数据库时钟比较租约，避免客户端时钟各说各话
- 库存更新和COMPLETED结果在同一个本地事务提交；外部支付副作用不在此保证之内，转到Saga/TCC
- 超时后按原键查询或重放结果，不重新生成键。已完成结果是该操作的原响应，不保证等于现在库存
- 重试包括尝试次数、总预算、每次剩余时间、可重试错误分类、指数退避和抖动；抖动分散同步重试但不增加容量

## ASCII机制图

```text
请求(key, fingerprint)
   |
 INSERT唯一键（自动提交；关闭连接释放重复键共享锁）
   | 登记后崩溃：保留原参数，空占位仍可重新领取
 新事务 SELECT FOR UPDATE
   +--参数冲突-----------------> 拒绝
   +--COMPLETED----------------> 返回原结果
   +--PENDING且租约未过--------> BUSY
   +--过期---------------------> owner新值, generation+1
                                      |
                         本地事务检查owner/代次/租约
                         库存条件更新 + COMPLETED结果
                                      |
                                  COMMIT
```

## 实际操作与逐步编码

1. 读Request校验与operations表结构，运行SQL合同测试观察OWNED、BUSY、REPLAY三条路径
2. 实现acquire：先独立登记，再在新事务锁定记录、检查参数、比较数据库时间租约、递增接管代次；不可把重复INSERT与FOR UPDATE合进同一事务形成共享锁升级
3. 实现complete：先验证持有者，再在同事务内条件扣库存与保存结果。库存不足保存-1这一稳定业务终态
4. 注入“库存更新后、结果提交前”故障，确认整个事务回滚且PENDING可在租约到期后接管
5. 强制实验记录lease_until=0模拟时间已到，旧owner即使恢复也不能提交。真实过期应由数据库时钟决定
6. 实现RetryBudget.execute，在固定种子随机源与逻辑时钟下验证预算递减、永久错误不重试、非幂等写不重试
7. 在登记提交后、授予租约前注入退出，重建Store后相同参数可立即领取，不同参数仍冲突；已绑定身份不可用新参数覆盖
8. 阅读TransactionRetry与测试：仅MySQL1213/40001且回滚没有不确定异常时，重新打开连接执行完整事务；最多4次，抖动上限依次5/10/20毫秒；COMMIT响应丢失、1205锁等待、永久错误不重试
9. 执行MySQL集成：屏障同时放行8个同键请求只产生1个OWNED；两行反序更新形成真实死锁，受害者重试完整事务后两行各增加2次；重启数据库后显式接收新Database并重建Store查询结果

以下命令用于源码仓库/公开源码包；Academy官方ZIP内用Check/Run或Gradle工具窗口执行同名任务。官方导出可能剔除Wrapper脚本/JAR，不能假设导入目录能直接运行./gradlew。独立服务课需同源shared/versions.env快照，缺失时不能视为发行完成。

本节单元检查：`./gradlew :05-idempotency:test`；完整调用端：`./gradlew :05-idempotency:run`。含数据库/消息服务的单元另执行 `./gradlew :05-idempotency:integrationTest`，Docker不可用应明确失败，不能跳过后当作通过。每次修改先跑对应方法测试，再跑全模块回归。

## 正确性合同与保证边界

H2仅验证SQL分支合同，不证明MySQL锁/断连语义。真实集成必须通过Docker MySQL。记录不会自动过期删除；生产保留期至少覆盖客户端重试/离线重放窗口，并有清理与审计约定。库存数值为实验整数，租约最大1分钟。TransactionRetry限制尝试次数与等待；每条SQL仍受JDBC查询/连接超时限制，不将其宣称为能强制取消任意事务的硬总时限。业务写操作在本地数据库内，不能直接推广到任意外部副作用。

## 固定版本源码阅读

- [mysql/mysql-connector-j 9.2.0：MysqlXAConnection.java](https://github.com/mysql/mysql-connector-j/blob/a3909bfeb62d5a517ab444bb88ba7ecf26100297/src/main/user-impl/java/com/mysql/cj/jdbc/MysqlXAConnection.java)
- [MySQL8.4语句锁与重复键共享锁](https://dev.mysql.com/doc/refman/8.4/en/innodb-locks-set.html)
- [MySQL8.4整事务死锁重试](https://dev.mysql.com/doc/refman/8.4/en/innodb-deadlocks-handling.html)

阅读任务：先在本节测试找到症状，再记录入口、关键状态、分支条件和返回/清理路径。每个结论附输入、版本、符号与反例。详细入口、关键状态、分支条件和实验证据对照见课程 docs/源码路线.md。源码字节哈希与标签解析结果在课程作者验证记录中公开；没有截图不伪称做过IDE断点。

## 公开完整标准解

完整Java文件位于本节 `solutions/`，与本节标准实现逐字同步，依赖接口、调用方和测试也在本节可见。下面列出全部编码区，便于先独立完成再核对；不需要解锁或另取私有分支。

### src/labs/distributed/idempotency/IdempotencyStore.java 的练习实现

```java
                if (!request.fingerprint().equals(rows.getString("fingerprint"))) {
                  throw new IllegalArgumentException("同一幂等键不能用于不同参数");
                }
                if (rows.getString("state").equals("COMPLETED")) {
                  return new Claim(
                      Kind.REPLAY,
                      rows.getString("owner"),
                      rows.getLong("generation"),
                      rows.getInt("result"));
                }
                long time = now(connection);
                if (rows.getLong("lease_until") > time) {
                  return new Claim(
                      Kind.BUSY, rows.getString("owner"), rows.getLong("generation"), 0);
                }
                long generation = rows.getLong("generation") + 1;
                Database.update(
                    connection,
                    "UPDATE operations SET owner=?, generation=?, lease_until=? WHERE op_key=?",
                    owner,
                    generation,
                    Math.addExact(time, lease.toMillis()),
                    request.key());
                return new Claim(Kind.OWNED, owner, generation, 0);
```
### src/labs/distributed/idempotency/IdempotencyStore.java 的练习实现

```java
            if (rows.getString("state").equals("COMPLETED")) return rows.getInt("result");
            if (claim.kind() != Kind.OWNED
                || !claim.owner().equals(rows.getString("owner"))
                || claim.generation() != rows.getLong("generation")
                || rows.getLong("lease_until") <= now(connection)) {
              throw new IllegalStateException("租约过期或已被接管，旧持有者禁止提交");
            }
            int changed =
                Database.update(
                    connection,
                    "UPDATE inventory SET available=available-? WHERE sku=? AND available>=?",
                    request.quantity(),
                    request.sku(),
                    request.quantity());
            int remaining = -1;
            if (changed == 1) {
              try (var stock =
                      Database.prepare(
                          connection,
                          "SELECT available FROM inventory WHERE sku=?",
                          request.sku());
                  var stocks = stock.executeQuery()) {
                stocks.next();
                remaining = stocks.getInt(1);
              }
            }
            failurePoint.afterStockUpdate();
            Database.update(
                connection,
                "UPDATE operations SET state='COMPLETED', result=? WHERE op_key=?",
                remaining,
                request.key());
            return remaining;
```
### src/labs/distributed/idempotency/RetryBudget.java 的练习实现

```java
    for (int attempt = 0; attempt < maxAttempts; attempt++) {
      long remaining = total.toNanos() - (clock.getAsLong() - start);
      if (remaining <= 0) break;
      try {
        return action.call(Duration.ofNanos(remaining));
      } catch (TransientFailure failure) {
        last = failure;
        if (!safeToRetry || attempt + 1 == maxAttempts) throw failure;
      }
      long base = baseBackoff.toNanos();
      long upper =
          base > (Long.MAX_VALUE >> attempt)
              ? maxBackoff.toNanos()
              : Math.min(maxBackoff.toNanos(), base << attempt);
      long delay = upper == 0 ? 0 : random.nextLong(upper);
      remaining = total.toNanos() - (clock.getAsLong() - start);
      if (remaining <= delay) break;
      sleeper.sleep(Duration.ofNanos(delay));
    }
    throw new TransientFailure("总预算耗尽，最后错误：" + (last == null ? "调用前已过期" : last.getMessage()));
```

## 标准解机制、复杂度与替代取舍

登记、领取、业务提交是三个独立短事务。登记成功即永久绑定原参数，尚未授予租约或扣库存；随后失败不会删除身份，可按原键恢复。领取事务锁定幂等行，业务事务再次验证owner+generation+lease并原子扣库存。重复INSERT的共享锁先释放，避免在同一事务升级为排他锁；剩余明确已回滚死锁只允许整事务有界重试。唯一约束是跨实例仲裁点。RetryBudget只捕获TransientFailure，永久错误直接传播；每次睡眠和重试都消耗同一个单调时钟预算。

## 面试机制、边界与深入追问

- 问：Redis SETNX足够实现业务幂等吗？答：不能独立覆盖锁过期、数据库提交后响应丢失与去重记录持久性；应明确原子提交边界
- 问：只有租约为什么不够？答：暂停进程恢复可能继续写，必须在真正写入资源处检查栅栏，单纯“我还持锁”声明无效
- 问：幂等记录过期可直接删吗？答：删除后晚到重试可能再次执行；保留期、客户端最大重试期与业务唯一约束需一起设计
- 问：为什么同键不同参数要拒绝？答：登记即固定业务身份，返回旧结果或失败后覆盖参数都会隐藏客户端错误。登记后未执行仍保留原参数；原参数可重新领取，不能永久PENDING
- 问：为何捕获重复键后马上FOR UPDATE仍会死锁？答：重复INSERT可持有共享锁，多个事务同时升级为排他锁产生环路；应缩短/分开登记事务，且只对已确认回滚的死锁整事务重试，不能吞异常或重放COMMIT未知请求
- 问：3层各尝试3次最坏多少？答：可达27次底层尝试；选择一层重试并传播预算，必要时再加共享重试令牌
- 迁移：把幂等作用域加入租户，补跨租户同key不冲突、同租户参数冲突和过期接管测试

## 三阶提示与独立验收

1. 基础提示：先列正常、边界、失败后的持久状态，找到测试的业务断言，不先复制实现
2. 机制提示：把每次外部提交、响应、日志落盘、资源归还画成独立事件，检查任意相邻事件间崩溃的后果
3. 深入提示：找真正执行原子操作的数据库/框架分支，确认幂等、锁、时间与持久化前提没有被内存模型替代

独立完成一个迁移题，补失败测试，解释一份错误实现被哪条断言拒绝，再做5分钟机制答辩。看过标准答案只记录“已阅读”，不能记录“独立掌握”。实际执行通过、未执行和已知边界见课程根中文阶段报告。
