# 04 Compose健康、持久化恢复与事故证据

## 本节要交付什么

本阶段把业务决策、依赖健康和恢复动作分开。MySQL不可用就不能可靠接单；Redis失败可绕过缓存；Kafka或gRPC失败时预算内可先写outbox。待发布事件和投影落后订单均纳入观察水位，达到1000时HTTP拒绝新单，取消仍可执行。这个水位是并发下的软准入阈值，不是跨节点精确计数配额。

实现decide并写阈值前后测试。Compose启动时等待依赖健康；运行中不能把“进程还活着”当作业务就绪。/api/ready检查数据库与积压，/api/health分别显示四项依赖。停止某个服务后页面应保留未知/失败状态，不能继续显示旧的绿色结论。

scripts/course.sh只按当前课程路径生成Compose项目名，stop不删卷，没有reset或down -v。Mac和Linux共用Docker Compose命令，完全不扫描PID，不会pkill系统Java。真实恢复脚本与CI必须读取根infra/versions.env七个键。修改共享版本台账是另一项版本变更，不能在本课偷偷换镜像。

## 先运行完整调用方

先scripts/course.sh start。提交一单但不重放，记录库存、outbox和订单号；pause-service mysql后请求应失败，recover-service mysql后同号查询恢复。再暂停delivery，发布后RPC失败；恢复delivery再重放，投影追平。每次只操作当前项目的命名服务。

从课程根运行 `./gradlew :04-recovery:test :04-recovery:usage`。实际数据库与网络验收用 `./gradlew :04-recovery:integrationTest`，需要Docker。完整网页调用用 `CAPSTONE_STAGE=04-recovery scripts/course.sh start`。所有测试和调用方都可见；不需要先抄完其他阶段的学习区。

```text
发现：RPC红色 + 投影落后
  -> 假设：订单未丢失，接收端不可用
  -> 验证：MySQL订单/事件存在，RPC探针失败
  -> 修复：恢复delivery，不删除队列和表
  -> 回归：重放原事件，inbox不重复，审计无ERROR
  -> 记录：版本、命令、时间、结果、尚未覆盖项
```

## 完整项目在哪里

本节只替换 `src/labs/capstone/RecoveryPolicy.java`。公共应用在 `app/src/main/java/labs/capstone/`，中文页面在 `app/src/main/resources/static/index.html`，五个公开标准实现在 `reference/<阶段名>/src/labs/capstone/`。每个标准实现使用独立源码根；Gradle和IDEA只为本节加入其余四阶段的标准实现，本节同名类始终来自学习区，防止测试绕过你的实现。`test/`与`integration-test/`是本节测试；`shared/`是可见的公共测试支撑。根README给出完整结构、接口与启动依赖。

## 逐步动手

1. 在纸上写出本节的失败分支，先预测每次调用是否允许推进状态
2. 运行现有测试，逐个实现学习区；为一个边界补充可见测试
3. 用Usage或页面实际调用，再运行真实集成；记录编译、快测、容器、浏览器各自结果
4. 不看下方答案，解释一个错误实现为什么会被你的新测试拒绝

## 递进提示

1. 先判断数据库，再判断积压边界，最后判断可降级的依赖；顺序表达业务优先级。
2. pending等于limit也应拒绝，不是只有超过才拒绝。缓存故障不应改变库存事实。
3. 重启保留卷；Testcontainers随机映射端口可能变化，因此恢复探测重新inspect端口。

## 核心源码与断点证据

阅读[SpringBoot3.5.16 ApplicationAvailabilityBean](https://github.com/spring-projects/spring-boot/blob/v3.5.16/spring-boot-project/spring-boot/src/main/java/org/springframework/boot/availability/ApplicationAvailabilityBean.java)。框架的生命周期状态不等于本项目的积压和依赖合同；本课另设业务探针。检查HealthMain的超时、RecoveryPolicy阈值，以及RealServices.restartMysql的端口重新发现。拿一次真实故障记录说明“启动成功”“存活”“就绪”“业务追平”的区别。

## 面试递进

**机制：为什么Redis坏了还能接单？**

缓存不是事实存储；事务仍在MySQL完成，代价是回源负载变大。

**边界：重放后outboxPending为0是否说明业务完成？**

不一定，事件已进Kafka但接收端可能落后，还要看投影版本、inbox与业务审计。

**取舍：为什么不自动清理积压？**

清空会丢失已提交的业务意图。应限流、恢复依赖、按同一身份重放，保留人工处置证据。

**追问：单机卷保留是否等于灾备？**

不是，宿主机或卷损坏仍可能丢数据；副本、备份恢复和跨可用区属于另外的验证。

## 标准答案与解释（直接可读）

下面是完整作者实现，不依赖折叠渲染或解锁。先对照关键分支，再重新独立实现；公开答案不会被导出排除。

```java
package labs.capstone;

import java.time.Duration;

/** C14-04：把接单就绪与下游积压分开；绝不能通过清空表来恢复。 */
public final class RecoveryPolicy {
    private RecoveryPolicy() {}

    public record Decision(boolean ready, boolean degraded, String action) {}

    public static Decision decide(
            boolean database, boolean redis, boolean kafka, boolean rpc, long pending, long limit) {
        // 学习区开始
        if (pending < 0 || limit < 1) throw new IllegalArgumentException("积压和容量上限不合法");
        if (!database) return new Decision(false, true, "暂停接单，检查MySQL连接与恢复状态");
        if (pending >= limit) return new Decision(false, true, "积压达到预算，拒绝新单并优先重放");
        if (!kafka || !rpc) return new Decision(true, true, "允许预算内接单，保留outbox并恢复下游");
        if (!redis) return new Decision(true, true, "绕过缓存查询MySQL，限制数据库压力");
        return new Decision(true, false, "正常接单并持续推进读模型");
        // 学习区结束
    }

    public static Duration retryDelay(int attempt) {
        if (attempt < 0) throw new IllegalArgumentException("重试次数不能为负");
        return Duration.ofMillis(250L << Math.min(attempt, 6));
    }
}
```

为什么这样实现：前面定义的业务状态、失败边界与源码分支必须对应到代码；每次确认都只能声明它前面的效果已经完成。测试既检查返回值，也检查持久化事实和不会发生的副作用。模仿代码排版不是目标，能用不同写法维持相同合同才算通过。
