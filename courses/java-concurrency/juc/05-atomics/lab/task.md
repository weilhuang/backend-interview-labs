# C02-05 · CAS与并发容器：额度、ABA和热点计数

预计90–150分钟；源码证据和独立迁移另留30–60分钟。主线统一完整JDK21、Gradle8.10.2、JUnit Jupiter5.11.4 / Platform1.11.4；不需要前端、Docker、数据库或外部账号。源码基线与当前运行JVM补丁版本分别记录。

## 先用起来：企业场景与接口合同

实现不透支额度预留、带版本更新槽和并发热点计数。reserve只接受正数，不足不改状态；add溢出不改状态。版本槽的expected来自snapshot，值比较遵循引用身份，stamp递增且溢出报错。计数不提供运行中的原子全局快照，所有写者结束后才要求精确最终合计。

作者工程保存完整参考实现；Academy学员占位区/普通学员副本从可编译的UnsupportedOperationException起步。完整答案、调用方与全部测试都随课提供。你可以先看答案再回测，但请把提示辅助与独立完成分开记录。

## 完整项目与运行入口

```text
05-atomics/lab/
+-- src/labs/AtomicLedger.java          # 实现接口与作者答案区
+-- src/labs/AtomicLedgerUsage.java     # 真实main调用方
+-- test/AtomicLedgerTest.java          # 全部可见契约测试
+-- solution/Alternative.java.txt # 另一种正确写法
+-- task.md                     # 教学步骤、源码、答案与追问
```

在课程根运行：

```sh
./gradlew :juc-05-atomics-lab:test
./gradlew :juc-05-atomics-lab:run
```

IDE中打开课程根或导入已由插件生成的课程归档；选项目SDK21和Gradle JVM21。普通源代码zip不是Academy归档。Check、提示、重置、归档导入的验证状态见根目录阶段报告，不能由命令行通过替代。

## 完整调用示例

```java
package labs;

public final class AtomicLedgerUsage {
    public static void main(String[] args) {
        var ledger = new AtomicLedger(3);
        System.out.println("预留2=" + ledger.reserve(2));
        System.out.println("再次预留2=" + ledger.reserve(2));
        var slot = new AtomicLedger.VersionedSlot("A");
        var old = slot.snapshot();
        slot.replace(old, "B");
        slot.replace(slot.snapshot(), old.value());
        System.out.println("旧版本更新=" + slot.replace(old, "C"));
        var counts = new AtomicLedger.Counters();
        counts.increment("订单");
        System.out.println("计数=" + counts.snapshot());
    }
}
```

先预测调用结果，再执行与测试比较。跨线程日志先后除非由代码建立关系，否则不构成契约；本课不按偶然调度顺序评分。

## 核心原理与ASCII图解

CAS只保证比较和替换这一瞬间，不保证“读取→计算→一次尝试”必然成功，所以失败要基于新值重算。预留的线性化点是成功CAS；余额不足时的读取也界定这次失败可发生的时刻。不要把数据库扣库存换成进程内AtomicInteger：重启、多个实例、持久化都没有覆盖。ABA不是值错误，而是只比较值无法识别中间历史。本槽将引用和版本一起比较，明确版本溢出边界。LongAdder把竞争分散到多个单元，sum不是对所有并发更新的原子快照，因此不能拿它的sum先检查再扣钱。

```text
读取余额old --> 检查足够? --否--> 返回false
       |是
       v
 CAS(old, old-amount) --失败--> 重新读取
       |成功
       v
    返回true

仅引用: A --> B --> A  旧A仍匹配
带版本: A/0 --> B/1 --> A/2  旧A/0不匹配
```

## 写代码、使用接口、验证结果

1. 运行额度调用端，列出非法参数和溢出后的状态要求
2. 写CAS重试；注意不能把减法放在循环外复用旧计算
3. 用顺序固定的A→B→A验证ABA，不依赖线程调度碰运气
4. 完成CHM的computeIfAbsent+LongAdder计数，等所有Future完成后核对合计
5. 设计AtomicLong/LongAdder的同负载JMH对照，仅作为O任务，记录读写比、线程数、预热/fork；禁止以必须快若干倍判分

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

- [AtomicInteger.java](https://github.com/openjdk/jdk/blob/890adb6410dab4606a4f26a942aed02fb2f55387/src/java.base/share/classes/java/util/concurrent/atomic/AtomicInteger.java)
- [AtomicStampedReference.java](https://github.com/openjdk/jdk/blob/890adb6410dab4606a4f26a942aed02fb2f55387/src/java.base/share/classes/java/util/concurrent/atomic/AtomicStampedReference.java)
- [LongAdder.java](https://github.com/openjdk/jdk/blob/890adb6410dab4606a4f26a942aed02fb2f55387/src/java.base/share/classes/java/util/concurrent/atomic/LongAdder.java)
- [Striped64.java](https://github.com/openjdk/jdk/blob/890adb6410dab4606a4f26a942aed02fb2f55387/src/java.base/share/classes/java/util/concurrent/atomic/Striped64.java)
- [ConcurrentHashMap.java](https://github.com/openjdk/jdk/blob/890adb6410dab4606a4f26a942aed02fb2f55387/src/java.base/share/classes/java/util/concurrent/ConcurrentHashMap.java)

追AtomicStampedReference内部不可变Pair与casPair：版本和值共同发布；引用比较不是String.equals。LongAdder.add先尝试base/已有Cell更新，冲突进入Striped64.longAccumulate；sum遍历base与cells，不是锁住所有写者的读取。ConcurrentHashMap.computeIfAbsent按槽状态走空槽CAS、预留或桶内同步等路径，回调要短，不能假设全表互斥；本例map不删除计数器。如果允许并发remove，已经取得旧LongAdder的线程可能更新脱离map的计数器，必须重新定义业务协议。

源码练习：打开对应原始文件，按上文符号设置断点或用IDE静态导航，记录“输入→入口→关键分支→状态变化→调用方观察”。记录失败/取消路径而不只截图类名。本课没有预制伪造断点截图；静态源码核对与动态调试分开填写。

## 标准答案与逐步解析

```java
package labs;

import java.util.*;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.*;

public final class AtomicLedger {
    private final AtomicInteger balance;

    public AtomicLedger(int initial) {
        if (initial < 0) throw new IllegalArgumentException("余额不能为负");
        balance = new AtomicInteger(initial);
    }

    public boolean reserve(int amount) {
        // 答案开始：CAS预留
        if (amount <= 0) throw new IllegalArgumentException("预留数量必须为正");
        for (; ; ) {
            int old = balance.get();
            if (old < amount) return false;
            if (balance.compareAndSet(old, old - amount)) return true;
        }
        // 答案结束：CAS预留
    }

    public void add(int amount) {
        if (amount <= 0) throw new IllegalArgumentException("添加数量必须为正");
        for (; ; ) {
            int old = balance.get();
            int next = Math.addExact(old, amount);
            if (balance.compareAndSet(old, next)) return;
        }
    }

    public int balance() {
        return balance.get();
    }

    public static final class VersionedSlot {
        public record Snapshot(String value, int version) {}

        private final AtomicStampedReference<String> value;

        public VersionedSlot(String initial) {
            value = new AtomicStampedReference<>(Objects.requireNonNull(initial), 0);
        }

        public Snapshot snapshot() {
            int[] stamp = {0};
            String ref = value.get(stamp);
            return new Snapshot(ref, stamp[0]);
        }

        public boolean replace(Snapshot expected, String next) {
            // 答案开始：防止ABA
            Objects.requireNonNull(expected);
            Objects.requireNonNull(next);
            return value.compareAndSet(
                    expected.value(),
                    next,
                    expected.version(),
                    Math.incrementExact(expected.version()));
            // 答案结束：防止ABA
        }
    }

    public static final class Counters {
        private final ConcurrentHashMap<String, LongAdder> counts = new ConcurrentHashMap<>();

        public void increment(String key) {
            // 答案开始：并发计数
            counts.computeIfAbsent(Objects.requireNonNull(key), ignored -> new LongAdder())
                    .increment();
            // 答案结束：并发计数
        }

        public long count(String key) {
            var counter = counts.get(Objects.requireNonNull(key));
            return counter == null ? 0 : counter.sum();
        }

        public Map<String, Long> snapshot() {
            var copy = new TreeMap<String, Long>();
            counts.forEach((key, counter) -> copy.put(key, counter.sum()));
            return Collections.unmodifiableMap(copy);
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

### 1. 机制：CAS失败为何必须重读？

参考表达：竞争者已改变前置状态，旧余额计算不再代表当前条件。

### 2. 边界：版本号永远解决ABA吗？

参考表达：不。有限位宽可能回绕，外部系统可能重用版本。本题用incrementExact拒绝溢出，真实系统需更长期的唯一代际策略。

### 3. 取舍：LongAdder能否作为余额？

参考表达：不适合需要线性化检查扣减的不变量；适合高竞争统计。sum并非运行时原子快照。

### 4. 追问：ConcurrentHashMap有了线程安全为何if(!containsKey)put仍会错？

参考表达：单次操作安全不等于复合业务原子。使用putIfAbsent/compute或更大事务边界。

## 独立迁移与完成标准

不看答案重新实现一种业务变体：保持本节安全不变量，增加一个明确的失败或关闭条件，并写最小测试击穿旧实现。回答“新增条件改变了哪个状态机、哪些等待者必须被通知、哪些完成信号可靠”。24小时后重写关键方法，记录是否需要提示。

完成条件：A全通过；机制、边界、证据、独立迁移各能给可检验说明。任何资源泄漏、静默丢任务、错误成功或不受限等待仍未解决则不完成。源代码仅用于合成实验数据，不对用户真实服务注入故障。
