# C02-04 · AQS源码：一次性门与共享同步

预计90–150分钟；源码证据和独立迁移另留30–60分钟。主线统一完整JDK21、Gradle8.10.2、JUnit Jupiter5.11.4 / Platform1.11.4；不需要前端、Docker、数据库或外部账号。源码基线与当前运行JVM补丁版本分别记录。

## 先用起来：企业场景与接口合同

教学实现一个只能从关闭变为打开的一次性门。open幂等并放行当前和未来所有等待者；await可中断；有界await超时返回false，零预算不阻塞；不支持重置、计数递减、独占所有者或Condition。随后用真实CountDownLatch记录完成数、Semaphore约束同时访问数。

作者工程保存完整参考实现；Academy学员占位区/普通学员副本从可编译的UnsupportedOperationException起步。完整答案、调用方与全部测试都随课提供。你可以先看答案再回测，但请把提示辅助与独立完成分开记录。

## 完整项目与运行入口

```text
04-aqs/lab/
+-- src/labs/OneShotGate.java          # 实现接口与作者答案区
+-- src/labs/OneShotGateUsage.java     # 真实main调用方
+-- test/OneShotGateTest.java          # 全部可见契约测试
+-- solution/Alternative.java.txt # 另一种正确写法
+-- task.md                     # 教学步骤、源码、答案与追问
```

**Academy官方归档导入模式**：用本题Check检查作答，打开对应Usage.java的main运行按钮，或用IDE的Gradle工具窗口执行test/run。Academy2026.9官方导出实际会剔除gradlew、gradlew.bat与gradle-wrapper.jar，仅保留properties；不要在缺少Wrapper的导入目录照抄终端./gradlew命令。项目SDK与Gradle JVM均用完整JDK21。

**源码仓库或普通Gradle学员副本模式**：以下./gradlew命令针对含Wrapper的课程根，Windows用gradlew.bat。完整CLI与诊断教程保留；首次依赖解析失败应区分环境问题与作答失败。

源码仓库终端运行：

```sh
./gradlew :juc-04-aqs-lab:test
./gradlew :juc-04-aqs-lab:run
```

IDE中打开课程根或导入已由插件生成的课程归档；选项目SDK21和Gradle JVM21。普通源代码zip不是Academy归档。Check、提示、重置、归档导入的验证状态见根目录阶段报告，不能由命令行通过替代。

## 完整调用示例

```java
package labs;

import java.util.concurrent.*;

public final class OneShotGateUsage {
    public static void main(String[] args) throws Exception {
        var gate = new OneShotGate();
        var done = new CountDownLatch(2);
        var permits = new Semaphore(1);
        try (var pool = Executors.newFixedThreadPool(2)) {
            for (int i = 0; i < 2; i++)
                pool.submit(
                        () -> {
                            try {
                                gate.await();
                                permits.acquire();
                                try {
                                    System.out.println("单许可执行区");
                                } finally {
                                    permits.release();
                                }
                            } catch (InterruptedException e) {
                                Thread.currentThread().interrupt();
                            } finally {
                                done.countDown();
                            }
                        });
            gate.open();
            if (!done.await(2, TimeUnit.SECONDS)) throw new IllegalStateException("任务未完成");
        }
        System.out.println("全部完成");
    }
}
```

先预测调用结果，再执行与测试比较。跨线程日志先后除非由代码建立关系，否则不构成契约；本课不按偶然调度顺序评分。

## 核心原理与ASCII图解

AQS将状态语义留给子类，把竞争、排队、停放、唤醒、超时和中断取消集中处理。本题state只有0/1；tryAcquireShared负值失败，非负值成功，共享成功允许其他等待者继续。releaseShared在tryReleaseShared返回true时传播唤醒；只把state写成1却不走释放协议，等待者可能一直park。isOpen只用于观察，不可用“先isOpen再await”拼出额外保证。门只开一次，所以没有代际重置和ABA；把它当可复用CyclicBarrier是契约错误。

```text
调用await --> tryAcquireShared(state) --成功--> 返回
                    |失败
                    v
             AQS共享等待节点 --> park
                    ^             |
open --> CAS 0到1 --> releaseShared唤醒 --> 重试获取

CountDownLatch: 完成数降到0     Semaphore: 当前可用许可数
```

## 写代码、使用接口、验证结果

1. 把门状态表写成0/1，列出所有合法转换
2. 填写两个钩子，先通过零预算与幂等测试
3. 让四个等待者看到open之前写入的42，并解释其发布关系
4. 中断一个等待者后再open，确认取消没有消耗其他人的资格
5. 跟进真实ReentrantLock获取失败入队路径，对比独占/共享与公平/非公平

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

- [AbstractQueuedSynchronizer.java](https://github.com/openjdk/jdk/blob/890adb6410dab4606a4f26a942aed02fb2f55387/src/java.base/share/classes/java/util/concurrent/locks/AbstractQueuedSynchronizer.java)
- [ReentrantLock.java](https://github.com/openjdk/jdk/blob/890adb6410dab4606a4f26a942aed02fb2f55387/src/java.base/share/classes/java/util/concurrent/locks/ReentrantLock.java)
- [CountDownLatch.java](https://github.com/openjdk/jdk/blob/890adb6410dab4606a4f26a942aed02fb2f55387/src/java.base/share/classes/java/util/concurrent/CountDownLatch.java)
- [Semaphore.java](https://github.com/openjdk/jdk/blob/890adb6410dab4606a4f26a942aed02fb2f55387/src/java.base/share/classes/java/util/concurrent/Semaphore.java)

在21+35定位AQS.acquireSharedInterruptibly → tryAcquireShared/acquire；acquire统一路径处理中断、超时、队列链接、park与重试。定位releaseShared → tryReleaseShared → signalNext，查看shared节点如何继续传播；不要拿旧版教程的Node常量名称代替本版字段。ReentrantLock.NonfairSync.initialTryLock 与 Sync.tryRelease：非公平初次CAS、重入计数、最后一次释放清空owner是不同分支；FairSync检查队列前驱并不保证OS调度顺序。CountDownLatch.Sync状态是剩余次数，Semaphore.Sync状态是许可数；相同框架承载不同语义。提交一张“入口/失败条件/队列变化/唤醒后重检”的断点记录，不把本题两行钩子称为重写AQS。

源码练习：打开对应原始文件，按上文符号设置断点或用IDE静态导航，记录“输入→入口→关键分支→状态变化→调用方观察”。记录失败/取消路径而不只截图类名。本课没有预制伪造断点截图；静态源码核对与动态调试分开填写。

## 标准答案与逐步解析

```java
package labs;

import java.time.Duration;
import java.util.Objects;
import java.util.concurrent.locks.AbstractQueuedSynchronizer;

public final class OneShotGate {
    private static final class Sync extends AbstractQueuedSynchronizer {
        protected int tryAcquireShared(int ignored) {
            // 答案开始：获取
            return getState() == 1 ? 1 : -1;
            // 答案结束：获取
        }

        protected boolean tryReleaseShared(int ignored) {
            // 答案开始：打开
            return compareAndSetState(0, 1);
            // 答案结束：打开
        }

        boolean opened() {
            return getState() == 1;
        }
    }

    private final Sync sync = new Sync();

    public void open() {
        sync.releaseShared(1);
    }

    public boolean isOpen() {
        return sync.opened();
    }

    public void await() throws InterruptedException {
        sync.acquireSharedInterruptibly(1);
    }

    public boolean await(Duration budget) throws InterruptedException {
        Objects.requireNonNull(budget);
        if (budget.isNegative()) throw new IllegalArgumentException("预算不能为负");
        return sync.tryAcquireSharedNanos(1, budget.toNanos());
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

### 1. 机制：AQS中的state到底是什么？

参考表达：它只是受控整型状态，具体语义由同步器定义：锁重入数、latch剩余数、信号量许可数等不同。

### 2. 边界：为什么不能给本门加reset就宣称可复用？

参考表达：旧等待者、新等待者与代际状态会混淆；需要定义阶段、到达数和取消语义。

### 3. 取舍：为什么业务更应优先CountDownLatch？

参考表达：成熟API有完整契约、维护和测试。自定义同步器只有明确缺口时才值得额外验证成本。

### 4. 追问：公平锁一定比非公平锁慢且绝不会饥饿吗？

参考表达：不能绝对化。通常有额外排队开销；线程调度与工作负载仍影响完成顺序，性能要同条件测量。

## 独立迁移与完成标准

不看答案重新实现一种业务变体：保持本节安全不变量，增加一个明确的失败或关闭条件，并写最小测试击穿旧实现。回答“新增条件改变了哪个状态机、哪些等待者必须被通知、哪些完成信号可靠”。24小时后重写关键方法，记录是否需要提示。

完成条件：A全通过；机制、边界、证据、独立迁移各能给可检验说明。任何资源泄漏、静默丢任务、错误成功或不受限等待仍未解决则不完成。源代码仅用于合成实验数据，不对用户真实服务注入故障。
