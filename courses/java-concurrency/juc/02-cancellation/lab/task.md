# C02-02 · 线程生命周期：协作取消与有界关闭

预计90–150分钟；源码证据和独立迁移另留30–60分钟。主线统一完整JDK21、Gradle8.10.2、JUnit Jupiter5.11.4 / Platform1.11.4；不需要前端、Docker、数据库或外部账号。源码基线与当前运行JVM补丁版本分别记录。

## 先用起来：企业场景与接口合同

实现任务终止控制器。必须先 start 再取消；重复 start 按 Thread 契约抛异常。cancelAndAwait 发出中断并在给定预算内等清理结束，零预算只发信号不等待；返回 true 表示工作和 cleanup 已完成。负预算/空预算报错。未响应中断的工作必须返回 false，不能 Thread.stop 或假装成功。

作者工程保存完整参考实现；Academy学员占位区/普通学员副本从可编译的UnsupportedOperationException起步。完整答案、调用方与全部测试都随课提供。你可以先看答案再回测，但请把提示辅助与独立完成分开记录。

## 完整项目与运行入口

```text
02-cancellation/lab/
+-- src/labs/CooperativeWorker.java          # 实现接口与作者答案区
+-- src/labs/CooperativeWorkerUsage.java     # 真实main调用方
+-- test/CooperativeWorkerTest.java          # 全部可见契约测试
+-- solution/Alternative.java.txt # 另一种正确写法
+-- task.md                     # 教学步骤、源码、答案与追问
```

在课程根运行：

```sh
./gradlew :juc-02-cancellation-lab:test
./gradlew :juc-02-cancellation-lab:run
```

IDE中打开课程根或导入已由插件生成的课程归档；选项目SDK21和Gradle JVM21。普通源代码zip不是Academy归档。Check、提示、重置、归档导入的验证状态见根目录阶段报告，不能由命令行通过替代。

## 完整调用示例

```java
package labs;

import java.time.Duration;
import java.util.concurrent.CountDownLatch;

public final class CooperativeWorkerUsage {
    public static void main(String[] args) throws Exception {
        var ready = new CountDownLatch(1);
        var worker =
                new CooperativeWorker(
                        () -> {
                            ready.countDown();
                            new CountDownLatch(1).await();
                        },
                        () -> System.out.println("资源已释放"));
        worker.start();
        ready.await();
        System.out.println("关闭完成=" + worker.cancelAndAwait(Duration.ofSeconds(2)));
    }
}
```

先预测调用结果，再执行与测试比较。跨线程日志先后除非由代码建立关系，否则不构成契约；本课不按偶然调度顺序评分。

## 核心原理与ASCII图解

中断不是从任意位置强行跳出。await/sleep等阻塞方法可以抛 InterruptedException 并清除标记；本例在线程最外层收到取消后恢复标记，结束任务。若方法可继续 throws InterruptedException，通常直接传播；若作为 Runnable 边界不能抛，必须采用合适的取消策略，不能简单空 catch 后继续。stopped 在 cleanup 完成后 countDown，因此调用者观察到 true 才能依赖资源已经归还。daemon只作为坏实现测试的最后退出保险，不能当关闭策略。

```text
NEW --start--> RUNNABLE --> 等待/工作
                        | interrupt 协作信号
                        v
                  捕获取消/业务异常
                        v
                   finally 清理 --> stopped信号
调用者: cancel --> 有界等待 --> 完成true / 尚未完成false
```

## 写代码、使用接口、验证结果

1. 先从调用端运行一个等待中的工作者，观察清理先于关闭完成输出
2. 实现取消方法：校验、发信号、有界等待，顺序不能倒置
3. 对忽略第一次中断的工作者做对照：用第二个latch决定何时放行，不用sleep猜状态
4. 让业务与cleanup分别抛异常，解释主故障保留策略
5. 补充业务循环里的 Thread.currentThread().isInterrupted 检查，并给每个外部I/O设置自身超时

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

- [Thread.java](https://github.com/openjdk/jdk/blob/890adb6410dab4606a4f26a942aed02fb2f55387/src/java.base/share/classes/java/lang/Thread.java)
- [CountDownLatch.java](https://github.com/openjdk/jdk/blob/890adb6410dab4606a4f26a942aed02fb2f55387/src/java.base/share/classes/java/util/concurrent/CountDownLatch.java)

定位 Thread.interrupt、isInterrupted、interrupted，并对照 InterruptedException 清除状态的调用契约。Thread 的状态是快照：RUNNABLE不代表当下在CPU上运行，WAITING不等于死锁。CountDownLatch.Sync.tryReleaseShared 在计数降到0时传播释放；await成功让取消方看见cleanup的写入。本实验保留业务故障，cleanup异常仅在没有主故障时记录；生产系统可用suppressed保留两者。不能在此声称future.cancel(true)保证底层网络请求结束。

源码练习：打开对应原始文件，按上文符号设置断点或用IDE静态导航，记录“输入→入口→关键分支→状态变化→调用方观察”。记录失败/取消路径而不只截图类名。本课没有预制伪造断点截图；静态源码核对与动态调试分开填写。

## 标准答案与逐步解析

```java
package labs;

import java.time.Duration;
import java.util.Objects;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicReference;

public final class CooperativeWorker {
    @FunctionalInterface
    public interface Work {
        void run() throws Exception;
    }

    private final CountDownLatch started = new CountDownLatch(1), stopped = new CountDownLatch(1);
    private final AtomicReference<Throwable> failure = new AtomicReference<>();
    private final Thread thread;

    public CooperativeWorker(Work work, Runnable cleanup) {
        Objects.requireNonNull(work);
        Objects.requireNonNull(cleanup);
        thread =
                Thread.ofPlatform()
                        .daemon()
                        .name("实验-可取消工作者")
                        .unstarted(
                                () -> {
                                    started.countDown();
                                    try {
                                        work.run();
                                    } catch (InterruptedException cancelled) {
                                        Thread.currentThread().interrupt();
                                    } catch (Throwable problem) {
                                        failure.set(problem);
                                    } finally {
                                        try {
                                            cleanup.run();
                                        } catch (Throwable problem) {
                                            failure.compareAndSet(null, problem);
                                        } finally {
                                            stopped.countDown();
                                        }
                                    }
                                });
    }

    public void start() {
        thread.start();
    }

    public boolean awaitStarted(Duration budget) throws InterruptedException {
        return started.await(nanos(budget), TimeUnit.NANOSECONDS);
    }

    public boolean awaitStopped(Duration budget) throws InterruptedException {
        return stopped.await(nanos(budget), TimeUnit.NANOSECONDS);
    }

    public boolean cancelAndAwait(Duration budget) throws InterruptedException {
        // 答案开始：取消
        long wait = nanos(budget);
        thread.interrupt();
        return stopped.await(wait, TimeUnit.NANOSECONDS);
        // 答案结束：取消
    }

    public Throwable failure() {
        return failure.get();
    }

    public boolean alive() {
        return thread.isAlive();
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

### 1. 机制：为什么先interrupt再await？

参考表达：先通知被等待的工作停止，否则可能互相等待。等待结束条件是清理后的latch。

### 2. 边界：捕获InterruptedException后何时恢复标记？

参考表达：不能传播且上层可能查询标记时通常恢复；若彻底处理取消并有明确约定，也可结束生命周期。不能无条件吞掉然后继续。

### 3. 取舍：为什么不只把线程设为daemon？

参考表达：JVM能退出不代表写入/事务/资源已完成。必须显式生命周期与失败状态。

### 4. 追问：取消HTTP调用仍不退出怎么办？

参考表达：设置连接/读取/整个请求deadline，使用客户端取消API；诊断阻塞位置，拒绝无界join，不用强杀线程替代协议。

## 独立迁移与完成标准

不看答案重新实现一种业务变体：保持本节安全不变量，增加一个明确的失败或关闭条件，并写最小测试击穿旧实现。回答“新增条件改变了哪个状态机、哪些等待者必须被通知、哪些完成信号可靠”。24小时后重写关键方法，记录是否需要提示。

完成条件：A全通过；机制、边界、证据、独立迁移各能给可检验说明。任何资源泄漏、静默丢任务、错误成功或不受限等待仍未解决则不完成。源代码仅用于合成实验数据，不对用户真实服务注入故障。
