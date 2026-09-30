# C02-06 · 线程池：饱和、拒绝、异常与关闭

预计90–150分钟；源码证据和独立迁移另留30–60分钟。主线统一完整JDK21、Gradle8.10.2、JUnit Jupiter5.11.4 / Platform1.11.4；不需要前端、Docker、数据库或外部账号。源码基线与当前运行JVM补丁版本分别记录。

## 先用起来：企业场景与接口合同

构建可复用有界执行器：先核心线程，再有界队列，再最大线程，超过容量抛RejectedExecutionException。Future显式传递业务异常。取消队列任务要回收队列容量。优雅预算耗尽后shutdownNow，并结束从队列取出的Future；返回false表示仍有任务未退出，不能声称中断已杀死所有任务。

作者工程保存完整参考实现；Academy学员占位区/普通学员副本从可编译的UnsupportedOperationException起步。完整答案、调用方与全部测试都随课提供。你可以先看答案再回测，但请把提示辅助与独立完成分开记录。

## 完整项目与运行入口

```text
06-executor/lab/
+-- src/labs/BoundedExecutor.java          # 实现接口与作者答案区
+-- src/labs/BoundedExecutorUsage.java     # 真实main调用方
+-- test/BoundedExecutorTest.java          # 全部可见契约测试
+-- solution/Alternative.java.txt # 另一种正确写法
+-- task.md                     # 教学步骤、源码、答案与追问
```

在课程根运行：

```sh
./gradlew :juc-06-executor-lab:test
./gradlew :juc-06-executor-lab:run
```

IDE中打开课程根或导入已由插件生成的课程归档；选项目SDK21和Gradle JVM21。普通源代码zip不是Academy归档。Check、提示、重置、归档导入的验证状态见根目录阶段报告，不能由命令行通过替代。

## 完整调用示例

```java
package labs;

import java.time.Duration;
import java.util.concurrent.TimeUnit;

public final class BoundedExecutorUsage {
    public static void main(String[] args) throws Exception {
        var pool = new BoundedExecutor(1, 2, 2);
        try {
            var future = pool.submit(() -> "订单已校验");
            System.out.println(future.get(2, TimeUnit.SECONDS));
        } finally {
            pool.shutdown(Duration.ofSeconds(2));
            System.out.println("池已退出=" + pool.awaitStopped(Duration.ofSeconds(2)));
        }
    }
}
```

先预测调用结果，再执行与测试比较。跨线程日志先后除非由代码建立关系，否则不构成契约；本课不按偶然调度顺序评分。

## 核心原理与ASCII图解

线程池控制的是线程与排队策略，不是业务成功保障。submit把任务包装为FutureTask，异常存入Future，若无人get/监听可能失去可见性。无界队列常使maximumPoolSize在通常饱和路径不生效：任务总能入队，就不会走扩展非核心线程的分支。CallerRunsPolicy会把延迟传递给提交方，可能在事件循环或持锁线程造成问题；DiscardPolicy可能让submit返回的Future永不完成。本课程使用AbortPolicy，业务层必须把拒绝转成明确响应或有界重试。shutdownNow只尽力中断运行任务，返回未启动任务；本封装还要cancel其Future。

```text
提交任务
   |
工作者 < core? --是--> 新核心线程
   |否
队列 offer成功? --是--> 排队 + 复查运行状态
   |否
工作者 < max? --是--> 新非核心线程
   |否
明确拒绝

关闭: shutdown -> 有界等待 -> shutdownNow + 取消未启动Future
```

## 写代码、使用接口、验证结果

1. 运行正常调用端，再读精确饱和测试中的三个latch步骤
2. 配置ArrayBlockingQueue与AbortPolicy，不允许换成默认无界队列
3. 实现cancelQueued，验证取消后新任务能立即占用空位
4. 实现两阶段关闭；区分已接收、已开始、已完成、已取消四个状态
5. 新增一个永不配合取消但由测试latch最终释放的任务，说明false的意义和应用级升级策略

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

- [ThreadPoolExecutor.java](https://github.com/openjdk/jdk/blob/890adb6410dab4606a4f26a942aed02fb2f55387/src/java.base/share/classes/java/util/concurrent/ThreadPoolExecutor.java)
- [FutureTask.java](https://github.com/openjdk/jdk/blob/890adb6410dab4606a4f26a942aed02fb2f55387/src/java.base/share/classes/java/util/concurrent/FutureTask.java)
- [AbstractExecutorService.java](https://github.com/openjdk/jdk/blob/890adb6410dab4606a4f26a942aed02fb2f55387/src/java.base/share/classes/java/util/concurrent/AbstractExecutorService.java)

逐段追ThreadPoolExecutor.execute的三步：addWorker(command,true)、workQueue.offer后复查、addWorker(command,false)/reject。看ctl如何组合runState与workerCount，不自行依赖私有位数。沿addWorker → Worker → runWorker → getTask，记录异常如何影响worker退出；再跟AbstractExecutorService.submit → newTaskFor → FutureTask.run/setException/get，解释为何submit异常通常不会直接到uncaughtExceptionHandler。关闭看interruptIdleWorkers、interruptWorkers、drainQueue；本课补上返回队列Future的取消，不宣称标准shutdownNow自动使每个Future进入终态。

源码练习：打开对应原始文件，按上文符号设置断点或用IDE静态导航，记录“输入→入口→关键分支→状态变化→调用方观察”。记录失败/取消路径而不只截图类名。本课没有预制伪造断点截图；静态源码核对与动态调试分开填写。

## 标准答案与逐步解析

```java
package labs;

import java.time.Duration;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicInteger;

public final class BoundedExecutor {
    private final ThreadPoolExecutor pool;

    public BoundedExecutor(int core, int max, int queueCapacity) {
        if (core < 1 || max < core || queueCapacity < 1)
            throw new IllegalArgumentException("线程和队列容量非法");
        AtomicInteger ids = new AtomicInteger();
        pool =
                new ThreadPoolExecutor(
                        core,
                        max,
                        30,
                        TimeUnit.SECONDS,
                        new ArrayBlockingQueue<>(queueCapacity),
                        task ->
                                Thread.ofPlatform()
                                        .daemon()
                                        .name("实验-有界池-" + ids.incrementAndGet())
                                        .unstarted(task),
                        new ThreadPoolExecutor.AbortPolicy());
    }

    public <T> Future<T> submit(Callable<T> job) {
        return pool.submit(Objects.requireNonNull(job));
    }

    public boolean cancelQueued(Future<?> job) {
        // 答案开始：取消清理
        boolean cancelled = Objects.requireNonNull(job).cancel(true);
        pool.purge();
        return cancelled;
        // 答案结束：取消清理
    }

    public boolean shutdown(Duration grace) throws InterruptedException {
        // 答案开始：有界关闭
        Objects.requireNonNull(grace);
        if (grace.isNegative()) throw new IllegalArgumentException("预算不能为负");
        pool.shutdown();
        if (pool.awaitTermination(grace.toNanos(), TimeUnit.NANOSECONDS)) return true;
        for (Runnable abandoned : pool.shutdownNow())
            if (abandoned instanceof Future<?> future) future.cancel(false);
        return pool.isTerminated();
        // 答案结束：有界关闭
    }

    public boolean awaitStopped(Duration budget) throws InterruptedException {
        Objects.requireNonNull(budget);
        if (budget.isNegative()) throw new IllegalArgumentException("预算不能为负");
        return pool.awaitTermination(budget.toNanos(), TimeUnit.NANOSECONDS);
    }

    public int queued() {
        return pool.getQueue().size();
    }

    public int workers() {
        return pool.getPoolSize();
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

### 1. 机制：core=1/max=2/queue=1时第四个阻塞任务为何拒绝？

参考表达：第1个占核心，第2个占队列，第3个扩最大线程，第4个无队列和工作者空间。

### 2. 边界：Future.cancel(true)返回true等于代码已经退出吗？

参考表达：不是。Future进入取消状态与底层协作停止是不同事件，仍要等待资源清理。

### 3. 取舍：为什么不能只加大队列？

参考表达：排队延迟、内存和超时放大；要根据服务率、deadline和背压策略定容量。

### 4. 追问：应用关闭后还有数据库写入怎么办？

参考表达：停止接单，跟踪在途，设置I/O期限与幂等补偿；先确认运行任务是否响应中断，不把进程存活当交付成功。

## 独立迁移与完成标准

不看答案重新实现一种业务变体：保持本节安全不变量，增加一个明确的失败或关闭条件，并写最小测试击穿旧实现。回答“新增条件改变了哪个状态机、哪些等待者必须被通知、哪些完成信号可靠”。24小时后重写关键方法，记录是否需要提示。

完成条件：A全通过；机制、边界、证据、独立迁移各能给可检验说明。任何资源泄漏、静默丢任务、错误成功或不受限等待仍未解决则不完成。源代码仅用于合成实验数据，不对用户真实服务注入故障。
