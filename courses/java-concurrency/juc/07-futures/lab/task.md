# C02-07 · 异步聚合：截止时间、降级、隔离与上下文

预计90–150分钟；源码证据和独立迁移另留30–60分钟。主线统一完整JDK21、Gradle8.10.2、JUnit Jupiter5.11.4 / Platform1.11.4；不需要前端、Docker、数据库或外部账号。源码基线与当前运行JVM补丁版本分别记录。

## 先用起来：企业场景与接口合同

做一个两下游聚合：主服务失败立即失败；次服务失败提供明确降级字符串；必须两者成功/降级且在总预算内才返回Summary。超时只结束聚合结果，不声称底层已取消。使用注入Timer做确定性测试，生产调用用RealTimer。异步请求使用显式Executor和Semaphore隔离，并在复用线程上设置与清理请求ID。

作者工程保存完整参考实现；Academy学员占位区/普通学员副本从可编译的UnsupportedOperationException起步。完整答案、调用方与全部测试都随课提供。你可以先看答案再回测，但请把提示辅助与独立完成分开记录。

## 完整项目与运行入口

```text
07-futures/lab/
+-- src/labs/AsyncGateway.java          # 实现接口与作者答案区
+-- src/labs/AsyncGatewayUsage.java     # 真实main调用方
+-- test/AsyncGatewayTest.java          # 全部可见契约测试
+-- solution/Alternative.java.txt # 另一种正确写法
+-- task.md                     # 教学步骤、源码、答案与追问
```

**Academy官方归档导入模式**：用本题Check检查作答，打开对应Usage.java的main运行按钮，或用IDE的Gradle工具窗口执行test/run。Academy2026.9官方导出实际会剔除gradlew、gradlew.bat与gradle-wrapper.jar，仅保留properties；不要在缺少Wrapper的导入目录照抄终端./gradlew命令。项目SDK与Gradle JVM均用完整JDK21。

**源码仓库或普通Gradle学员副本模式**：以下./gradlew命令针对含Wrapper的课程根，Windows用gradlew.bat。完整CLI与诊断教程保留；首次依赖解析失败应区分环境问题与作答失败。

源码仓库终端运行：

```sh
./gradlew :juc-07-futures-lab:test
./gradlew :juc-07-futures-lab:run
```

IDE中打开课程根或导入已由插件生成的课程归档；选项目SDK21和Gradle JVM21。普通源代码zip不是Academy归档。Check、提示、重置、归档导入的验证状态见根目录阶段报告，不能由命令行通过替代。

## 完整调用示例

```java
package labs;

import java.time.Duration;
import java.util.concurrent.*;

public final class AsyncGatewayUsage {
    public static void main(String[] args) throws Exception {
        try (var pool = Executors.newFixedThreadPool(2);
                var timer = new AsyncGateway.RealTimer()) {
            var gateway = new AsyncGateway(pool, 2);
            var order = gateway.request("请求-42", () -> "订单:" + gateway.currentRequest());
            var recommendation =
                    gateway.<String>request(
                            "请求-42",
                            () -> {
                                throw new IllegalStateException("推荐暂不可用");
                            });
            System.out.println(
                    AsyncGateway.aggregate(order, recommendation, Duration.ofSeconds(2), timer)
                            .get(3, TimeUnit.SECONDS));
        }
    }
}
```

先预测调用结果，再执行与测试比较。跨线程日志先后除非由代码建立关系，否则不构成契约；本课不按偶然调度顺序评分。

## 核心原理与ASCII图解

CompletableFuture描述完成依赖，不天然拥有底层阻塞操作。orTimeout、completeOnTimeout或本题的计时器都不能自动中止HTTP客户端；如需取消，应另持有客户端请求句柄并把剩余预算传给连接、读、请求各层。thenCombine需要双方结果，本题额外监听主服务错误，避免主失败却继续等可选服务。回调默认可在完成线程执行，不能在其中偷偷做耗时阻塞。隔离舱在任务提交前拿许可，执行器拒绝也必须归还；任务完成/异常finally恢复原上下文以兼容嵌套调用。

```text
主服务 --------------------+--> thenCombine --> 聚合结果
   |失败即终止              |
次服务 --> 失败转显式降级 --+
                              ^
总预算计时器 --超时异常---------+

请求ID + 许可 --> 显式执行器 --> 设置上下文 --> 业务
                                          | finally
                                     恢复上下文 + 归还许可
```

## 写代码、使用接口、验证结果

1. 先运行调用端得到含降级的Summary，确认主/次服务的业务差异
2. 实现aggregate，通过手动timer.expire测试截止时间，不等待真实秒数
3. 让主服务失败而次服务永远pending，验证主失败立即可见
4. 实现隔离与上下文，测试排队线程复用、业务异常、执行器拒绝
5. 取消返回的CompletableFuture，观察底层仍执行；写出客户端级取消与剩余deadline传播方案

先写清不变量，再填写答案区，先跑单任务test，再run，最后根目录test。测试红色时区分编译/合同错误、环境无效、超时未退出；不要通过加sleep、无限增大超时或删断言“修好”并发。测试的2–3秒等待只是死锁/调度故障护栏，不是性能SLA。

## 可选提示

<div class="hint" title="H1：找到关键状态">
列出哪些状态必须一起变化，哪些API只提供单次原子性。先看失败测试中的最小输入和前置条件。
</div>
<div class="hint" title="H2：跟随最小交错">
按照上图模拟成功、失败、关闭、取消四条路径；检查所有资源从哪里获得、在哪里归还。
</div>
<div class="hint" title="H3：对照局部机制">
先写合同校验，再实现状态转换。等待用条件循环，资源清理用finally；具体适用性以本节完整接口为准。
</div>
<div class="hint" title="H4：完整参考解">
下方公开标准解与Alternative文件可直接阅读；无需先通过题目。
</div>

## 真实源码定位与机制分析（R）

固定OpenJDK21 GA tag jdk-21+35，已核对commit 890adb6410dab4606a4f26a942aed02fb2f55387。正式API行为以Java21文档为准，私有实现只在这个commit下讲解。若运行的是21u修补版，必须把版本差异写入证据，不能伪称调试的就是GA二进制。

- [CompletableFuture.java](https://github.com/openjdk/jdk/blob/890adb6410dab4606a4f26a942aed02fb2f55387/src/java.base/share/classes/java/util/concurrent/CompletableFuture.java)
- [ThreadLocalRandom.java](https://github.com/openjdk/jdk/blob/890adb6410dab4606a4f26a942aed02fb2f55387/src/java.base/share/classes/java/util/concurrent/ThreadLocalRandom.java)
- [ThreadLocal.java](https://github.com/openjdk/jdk/blob/890adb6410dab4606a4f26a942aed02fb2f55387/src/java.base/share/classes/java/lang/ThreadLocal.java)

定位CompletableFuture.uniWhenComplete、biApply/biApplyStage、completeExceptionally、cancel和orTimeout。完成节点登记与结果CAS决定谁赢得完成竞态；失败不会回滚其他下游已经发生的副作用。读取源码中cancel的mayInterruptIfRunning说明：它不是像FutureTask那样拥有运行线程。ThreadLocal.remove走ThreadLocalMap.remove/expungeStaleEntry，弱引用key也不意味着value立即释放。此处通过显式remove/恢复值避免请求串号；InheritableThreadLocal在线程池中不等价于逐请求上下文传播。

源码练习：打开对应原始文件，按上文符号设置断点或用IDE静态导航，记录“输入→入口→关键分支→状态变化→调用方观察”。记录失败/取消路径而不只截图类名。本课没有预制伪造断点截图；静态源码核对与动态调试分开填写。

## 标准答案与逐步解析

```java
package labs;

import java.time.Duration;
import java.util.Objects;
import java.util.concurrent.*;
import java.util.function.Supplier;

public final class AsyncGateway {
    public record Summary(String primary, String secondary) {}

    @FunctionalInterface
    public interface Ticket {
        void cancel();
    }

    @FunctionalInterface
    public interface Timer {
        Ticket schedule(Duration delay, Runnable action);
    }

    public static final class RealTimer implements Timer, AutoCloseable {
        private final ScheduledExecutorService scheduler =
                Executors.newSingleThreadScheduledExecutor(
                        r -> Thread.ofPlatform().daemon().name("实验-期限计时器").unstarted(r));

        public Ticket schedule(Duration delay, Runnable action) {
            var future = scheduler.schedule(action, nanos(delay), TimeUnit.NANOSECONDS);
            return () -> future.cancel(false);
        }

        public void close() {
            scheduler.shutdownNow();
        }
    }

    public static CompletableFuture<Summary> aggregate(
            CompletableFuture<String> primary,
            CompletableFuture<String> secondary,
            Duration budget,
            Timer timer) {
        // 答案开始：有界聚合
        Objects.requireNonNull(primary);
        Objects.requireNonNull(secondary);
        Objects.requireNonNull(timer);
        nanos(budget);
        var result = new CompletableFuture<Summary>();
        Ticket alarm =
                timer.schedule(
                        budget,
                        () -> result.completeExceptionally(new TimeoutException("聚合已超过预算")));
        result.whenComplete((value, error) -> alarm.cancel());
        primary.whenComplete(
                (value, error) -> {
                    if (error != null) result.completeExceptionally(error);
                });
        primary.thenCombine(secondary.exceptionally(error -> "次要服务降级"), Summary::new)
                .whenComplete(
                        (value, error) -> {
                            if (error == null) result.complete(value);
                            else result.completeExceptionally(error);
                        });
        return result;
        // 答案结束：有界聚合
    }

    private final Executor executor;
    private final Semaphore permits;
    private final ThreadLocal<String> request = new ThreadLocal<>();

    public AsyncGateway(Executor executor, int concurrency) {
        this.executor = Objects.requireNonNull(executor);
        if (concurrency < 1) throw new IllegalArgumentException("并发上限必须为正");
        permits = new Semaphore(concurrency);
    }

    public String currentRequest() {
        return request.get();
    }

    public <T> CompletableFuture<T> request(String id, Supplier<T> action) {
        // 答案开始：隔离和上下文
        Objects.requireNonNull(id);
        Objects.requireNonNull(action);
        var result = new CompletableFuture<T>();
        if (!permits.tryAcquire()) {
            result.completeExceptionally(new RejectedExecutionException("下游隔离舱已满"));
            return result;
        }
        try {
            executor.execute(
                    () -> {
                        String previous = request.get();
                        request.set(id);
                        try {
                            result.complete(action.get());
                        } catch (Throwable error) {
                            result.completeExceptionally(error);
                        } finally {
                            if (previous == null) request.remove();
                            else request.set(previous);
                            permits.release();
                        }
                    });
        } catch (RuntimeException rejected) {
            permits.release();
            result.completeExceptionally(rejected);
        }
        return result;
        // 答案结束：隔离和上下文
    }

    private static long nanos(Duration budget) {
        Objects.requireNonNull(budget);
        if (budget.isNegative()) throw new IllegalArgumentException("预算不能为负");
        return budget.toNanos();
    }
}
```

解析顺序：
1. 对照接口合同确认非法输入在修改状态前被拒绝
2. 逐行标出线性化点或发布边；不存在单一原子快照的地方要明确注明
3. 追踪等待/取消/失败路径与finally资源清理，解释何时真正完成
4. 读全部测试，指出每个断言保障哪个合同；参考实现并不是唯一合法字段布局
5. 对照公开Alternative.java.txt，再考虑新的边界；替代解是回归对照，不要求强制模仿某一风格

本单元具体算法与复杂度边界以上文机制和源码为准。阻塞等待的耗时取决于外部进展，不能因为方法体短就宣称“最坏O(1)且一定完成”；锁或CAS也不能保证每个线程在固定时间内获胜。

## 自动验收与观察验收分开

- A：本节所有可见JUnit测试；作者质量门禁还运行未填写起点和已知错误变体，确认测试能发现问题
- O：提交源码路线、happens-before/资源图、一次失败原因链及迁移说明；性能、调度、JFR样本均为证据，不按固定快慢判分
- R：原始源码commit、文件、符号与实际观察一致；只有静态阅读时明确标“动态断点未运行”
- T：自写模型只承诺本节接口；没有宣称实现完整JDK同步器、分布式事务或生产调度器

证据文件可按docs/证据模板.md填写。正确性测试通过不等于机制理解或源码任务完成。环境缺失记BLOCKED，没运行记NOT_RUN，不能汇总为PASS。

## 面试题递进与参考表达

### 1. 机制：为什么超时之后主服务仍可能写数据库？

参考表达：完成future和停止外部操作是两条控制链；超时结果不会撤销副作用。需要deadline、显式取消和幂等业务协议。

### 2. 边界：所有异常都降级合理吗？

参考表达：不。合同区分核心依赖和可选依赖，权限/数据损坏等不能随意伪造成成功。

### 3. 取舍：为什么不用默认commonPool？

参考表达：阻塞I/O可能占满共享池并干扰无关任务；显式执行器能控制容量与生命周期。

### 4. 追问：ThreadLocal.clear放在成功分支够吗？

参考表达：不够，异常和取消路径也会复用线程。finally恢复原值可支持嵌套调用。

## 独立迁移与完成标准

不看答案重新实现一种业务变体：保持本节安全不变量，增加一个明确的失败或关闭条件，并写最小测试击穿旧实现。回答“新增条件改变了哪个状态机、哪些等待者必须被通知、哪些完成信号可靠”。24小时后重写关键方法，记录是否需要提示。

完成条件：A全通过；机制、边界、证据、独立迁移各能给可检验说明。任何资源泄漏、静默丢任务、错误成功或不受限等待仍未解决则不完成。源代码仅用于合成实验数据，不对用户真实服务注入故障。
