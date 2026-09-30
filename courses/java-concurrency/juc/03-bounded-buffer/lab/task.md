# C02-03 · monitor与Condition：可关闭有界缓冲区

预计90–150分钟；源码证据和独立迁移另留30–60分钟。主线统一完整JDK21、Gradle8.10.2、JUnit Jupiter5.11.4 / Platform1.11.4；不需要前端、Docker、数据库或外部账号。源码基线与当前运行JVM补丁版本分别记录。

## 先用起来：企业场景与接口合同

为订单后台流水线写两种同契约有界队列。FIFO，不接收null，容量大于0。满时put等待，空时take等待。close幂等：拒绝新put，已有元素可继续取完；关闭且空时take返回Optional.empty。关闭必须唤醒所有等待者；中断可传播；不承诺公平排队。

作者工程保存完整参考实现；Academy学员占位区/普通学员副本从可编译的UnsupportedOperationException起步。完整答案、调用方与全部测试都随课提供。你可以先看答案再回测，但请把提示辅助与独立完成分开记录。

## 完整项目与运行入口

```text
03-bounded-buffer/lab/
+-- src/labs/BoundedBuffers.java          # 实现接口与作者答案区
+-- src/labs/BoundedBuffersUsage.java     # 真实main调用方
+-- test/BoundedBuffersTest.java          # 全部可见契约测试
+-- solution/Alternative.java.txt # 另一种正确写法
+-- task.md                     # 教学步骤、源码、答案与追问
```

**Academy官方归档导入模式**：用本题Check检查作答，打开对应Usage.java的main运行按钮，或用IDE的Gradle工具窗口执行test/run。Academy2026.9官方导出实际会剔除gradlew、gradlew.bat与gradle-wrapper.jar，仅保留properties；不要在缺少Wrapper的导入目录照抄终端./gradlew命令。项目SDK与Gradle JVM均用完整JDK21。

**源码仓库或普通Gradle学员副本模式**：以下./gradlew命令针对含Wrapper的课程根，Windows用gradlew.bat。完整CLI与诊断教程保留；首次依赖解析失败应区分环境问题与作答失败。

源码仓库终端运行：

```sh
./gradlew :juc-03-bounded-buffer-lab:test
./gradlew :juc-03-bounded-buffer-lab:run
```

IDE中打开课程根或导入已由插件生成的课程归档；选项目SDK21和Gradle JVM21。普通源代码zip不是Academy归档。Check、提示、重置、归档导入的验证状态见根目录阶段报告，不能由命令行通过替代。

## 完整调用示例

```java
package labs;

public final class BoundedBuffersUsage {
    public static void main(String[] args) throws Exception {
        for (BoundedBuffers.Buffer<String> b :
                java.util.List.<BoundedBuffers.Buffer<String>>of(
                        new BoundedBuffers.MonitorBuffer<>(2),
                        new BoundedBuffers.LockBuffer<>(2))) {
            b.put("订单-1");
            b.put("订单-2");
            b.close();
            for (var value = b.take(); value.isPresent(); value = b.take())
                System.out.println(value.get());
            System.out.println("已排空且关闭");
        }
    }
}
```

先预测调用结果，再执行与测试比较。跨线程日志先后除非由代码建立关系，否则不构成契约；本课不按偶然调度顺序评分。

## 核心原理与ASCII图解

条件队列里等待的是“可能有空间/数据”这件事，不是一次唤醒就永久获得资格。wait/await释放当前锁，返回前重新获取，所以醒来必须在while内重新判断。monitor只有一个wait set，notify可能叫醒不合适的一类等待者，参考解使用notifyAll。显式锁将notEmpty与notFull分组，正常单次操作signal对应等待组，close则对两组signalAll。公平锁不等于OS调度公平，且可能牺牲吞吐。两个版本共享的是契约，不是完全相同的中断能力：synchronized的锁获取本身不可中断，lockInterruptibly可以。

```text
生产者 --持锁检查 满?--是--> notFull等待 --重新取锁--> 再检查
                 |否
                 v
               入队 --signal--> notEmpty等待的消费者

close: 关闭标记 + 唤醒两类等待者
       已有元素继续排空；空且关闭 -> 结束
```

## 写代码、使用接口、验证结果

1. 先用容量2顺序put/take运行调用端，明确close不是清空
2. 依次写MonitorBuffer.put/take并保证检查与修改都在同一把锁
3. 写LockBuffer等价实现，把unlock放在finally
4. 阅读测试中的满队列生产者/空队列消费者关闭场景，增加多等待者变体
5. 画两把锁交叉获取的环路，提出全局锁顺序或缩小临界区方案，不在测试进程制造永久死锁

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

- [ArrayBlockingQueue.java](https://github.com/openjdk/jdk/blob/890adb6410dab4606a4f26a942aed02fb2f55387/src/java.base/share/classes/java/util/concurrent/ArrayBlockingQueue.java)
- [ReentrantLock.java](https://github.com/openjdk/jdk/blob/890adb6410dab4606a4f26a942aed02fb2f55387/src/java.base/share/classes/java/util/concurrent/locks/ReentrantLock.java)
- [AbstractQueuedSynchronizer.java](https://github.com/openjdk/jdk/blob/890adb6410dab4606a4f26a942aed02fb2f55387/src/java.base/share/classes/java/util/concurrent/locks/AbstractQueuedSynchronizer.java)

ArrayBlockingQueue.put/take的while、await和enqueue/dequeue对应本题容量不变量；该JDK队列本身没有此处的close协议，不能逐字替换。ReentrantLock.newCondition返回AQS.ConditionObject。追ConditionObject.await、signal、enableWait、acquire，区分条件队列与同步获取队列：signal把资格转为争锁，不是直接把锁交给对方。异常路径必须重新获得锁后再按约定抛出/恢复中断。源码私有字段随版本变化，本课只钉住21+35。

源码练习：打开对应原始文件，按上文符号设置断点或用IDE静态导航，记录“输入→入口→关键分支→状态变化→调用方观察”。记录失败/取消路径而不只截图类名。本课没有预制伪造断点截图；静态源码核对与动态调试分开填写。

## 标准答案与逐步解析

```java
package labs;

import java.util.*;
import java.util.concurrent.locks.*;

public final class BoundedBuffers {
    private BoundedBuffers() {}

    public interface Buffer<T> {
        void put(T value) throws InterruptedException;

        Optional<T> take() throws InterruptedException;

        void close();

        int size();
    }

    public static final class MonitorBuffer<T> implements Buffer<T> {
        private final int capacity;
        private final Deque<T> queue = new ArrayDeque<>();
        private boolean closed;

        public MonitorBuffer(int capacity) {
            if (capacity < 1) throw new IllegalArgumentException("容量必须为正");
            this.capacity = capacity;
        }

        public synchronized void put(T value) throws InterruptedException {
            // 答案开始：监视器放入
            Objects.requireNonNull(value);
            while (queue.size() == capacity && !closed) wait();
            if (closed) throw new IllegalStateException("缓冲区已关闭");
            queue.addLast(value);
            notifyAll();
            // 答案结束：监视器放入
        }

        public synchronized Optional<T> take() throws InterruptedException {
            // 答案开始：监视器取出
            while (queue.isEmpty() && !closed) wait();
            if (queue.isEmpty()) return Optional.empty();
            T value = queue.removeFirst();
            notifyAll();
            return Optional.of(value);
            // 答案结束：监视器取出
        }

        public synchronized void close() {
            closed = true;
            notifyAll();
        }

        public synchronized int size() {
            return queue.size();
        }
    }

    public static final class LockBuffer<T> implements Buffer<T> {
        private final int capacity;
        private final Deque<T> queue = new ArrayDeque<>();
        private final ReentrantLock lock = new ReentrantLock();
        private final Condition notEmpty = lock.newCondition(), notFull = lock.newCondition();
        private boolean closed;

        public LockBuffer(int capacity) {
            if (capacity < 1) throw new IllegalArgumentException("容量必须为正");
            this.capacity = capacity;
        }

        public void put(T value) throws InterruptedException {
            // 答案开始：显式锁放入
            Objects.requireNonNull(value);
            lock.lockInterruptibly();
            try {
                while (queue.size() == capacity && !closed) notFull.await();
                if (closed) throw new IllegalStateException("缓冲区已关闭");
                queue.addLast(value);
                notEmpty.signal();
            } finally {
                lock.unlock();
            }
            // 答案结束：显式锁放入
        }

        public Optional<T> take() throws InterruptedException {
            // 答案开始：显式锁取出
            lock.lockInterruptibly();
            try {
                while (queue.isEmpty() && !closed) notEmpty.await();
                if (queue.isEmpty()) return Optional.empty();
                T value = queue.removeFirst();
                notFull.signal();
                return Optional.of(value);
            } finally {
                lock.unlock();
            }
            // 答案结束：显式锁取出
        }

        public void close() {
            lock.lock();
            try {
                closed = true;
                notEmpty.signalAll();
                notFull.signalAll();
            } finally {
                lock.unlock();
            }
        }

        public int size() {
            lock.lock();
            try {
                return queue.size();
            } finally {
                lock.unlock();
            }
        }
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

### 1. 机制：为什么if改成while有实质差别？

参考表达：虚假唤醒、竞争者先拿走资源、关闭等都会使醒来时条件仍不满足，必须重新检查。

### 2. 边界：close后为何还返回旧元素？

参考表达：这是明确的排空式关闭契约。若业务要求立即丢弃，应新定义取消策略与丢弃回调。

### 3. 取舍：notifyAll会不会有惊群？

参考表达：会有额外唤醒和争锁；单wait set下更容易保证活性。Condition按条件分组减少无用唤醒。

### 4. 追问：队列FIFO是否保证消费者按开始等待顺序服务？

参考表达：不保证。元素顺序、锁公平性、线程调度是不同层次。

## 独立迁移与完成标准

不看答案重新实现一种业务变体：保持本节安全不变量，增加一个明确的失败或关闭条件，并写最小测试击穿旧实现。回答“新增条件改变了哪个状态机、哪些等待者必须被通知、哪些完成信号可靠”。24小时后重写关键方法，记录是否需要提示。

完成条件：A全通过；机制、边界、证据、独立迁移各能给可检验说明。任何资源泄漏、静默丢任务、错误成功或不受限等待仍未解决则不完成。源代码仅用于合成实验数据，不对用户真实服务注入故障。
