# C02-01 · JMM：安全发布与复合原子性

预计90–150分钟；源码证据和独立迁移另留30–60分钟。主线统一完整JDK21、Gradle8.10.2、JUnit Jupiter5.11.4 / Platform1.11.4；不需要前端、Docker、数据库或外部账号。源码基线与当前运行JVM补丁版本分别记录。

## 先用起来：企业场景与接口合同

做一个路由快照发布器和受理计数器。调用者可修改原始列表，但已经发布的配置不能变化；一次读必须得到同一代完整快照。本课限定生命周期最多Integer.MAX_VALUE次accept，范围内每次返回从1开始的唯一序号；超长运行生产服务需另定溢出策略。并列完成受控丢更新反例。

作者工程保存完整参考实现；Academy学员占位区/普通学员副本从可编译的UnsupportedOperationException起步。完整答案、调用方与全部测试都随课提供。你可以先看答案再回测，但请把提示辅助与独立完成分开记录。

## 完整项目与运行入口

```text
01-publication/lab/
+-- src/labs/PublicationLab.java          # 实现接口与作者答案区
+-- src/labs/PublicationLabUsage.java     # 真实main调用方
+-- test/PublicationLabTest.java          # 全部可见契约测试
+-- solution/Alternative.java.txt # 另一种正确写法
+-- task.md                     # 教学步骤、源码、答案与追问
```

在课程根运行：

```sh
./gradlew :juc-01-publication-lab:test
./gradlew :juc-01-publication-lab:run
```

IDE中打开课程根或导入已由插件生成的课程归档；选项目SDK21和Gradle JVM21。普通源代码zip不是Academy归档。Check、提示、重置、归档导入的验证状态见根目录阶段报告，不能由命令行通过替代。

## 完整调用示例

```java
package labs;

import java.util.List;

public final class PublicationLabUsage {
    public static void main(String[] args) throws Exception {
        var lab = new PublicationLab();
        lab.publish(new PublicationLab.Snapshot(1, List.of("/orders")));
        System.out.println("配置=" + lab.current());
        System.out.println("受理序号=" + lab.accept());
        System.out.println("受控错误计数=" + PublicationLab.forcedLostUpdate());
    }
}
```

先预测调用结果，再执行与测试比较。跨线程日志先后除非由代码建立关系，否则不构成契约；本课不按偶然调度顺序评分。

## 核心原理与ASCII图解

可见性、原子性、有序性是三个问题。将不可变 Snapshot 经 volatile 引用发布，读者只读一次引用，再使用该快照，避免把两代配置的字段拼起来。record 的字段是 final，但 List 仍可能是可变对象，必须防御性复制。final 字段语义不能允许构造期间 this 逃逸，也不等同于自动发布所有后来写入。accepted.incrementAndGet 的线性化点由原子更新提供；volatile int 上的读取、加一、写回仍是多个动作。forcedLostUpdate 故意加栅栏，证明这个复合操作的逻辑漏洞，不是用同步工具“测试到真实弱内存重排”。

```text
写者: 构造完整快照 --> volatile 写 current
                              | happens-before
读者:                  volatile 读 current --> 读取不可变字段

错误计数: 甲读0 --+--> 甲写1
                 |
          乙读0 --+--> 乙写1   最终1，缺少一个完整的原子更新
```

## 写代码、使用接口、验证结果

1. 先运行调用端，画出路由版本与列表的成对关系
2. 填写 publish 与 accept；不要在读取端拆成两次 current() 后取不同字段
3. 修改调用方原始列表，证明已发布快照不变
4. 运行受控丢更新；去掉 volatile 是否修复？解释答案
5. 画出程序次序、volatile synchronizes-with、传递关系；列出 Thread.start/join 和锁释放/获取的其他发布方式

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

固定源码中追 AtomicInteger.incrementAndGet → Unsafe.getAndAddInt。不要把 Java 层没有显式循环误解为没有原子硬件/VM支持。对照 JLS21 17.4.5 与17.5：volatile边和final字段规则解决的前提不同。测试中的 Future.get/join 也产生可见性边，因此“读到了正确值”不能单独证明 publish 必须为volatile。字段删除volatile的弱内存错误只做O类审阅，不编造每次必失败的测试。需要 jcstress 时另建工具实验并记录JVM/架构/重复次数。

源码练习：打开对应原始文件，按上文符号设置断点或用IDE静态导航，记录“输入→入口→关键分支→状态变化→调用方观察”。记录失败/取消路径而不只截图类名。本课没有预制伪造断点截图；静态源码核对与动态调试分开填写。

## 标准答案与逐步解析

```java
package labs;

import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicInteger;

public final class PublicationLab {
    public record Snapshot(int version, List<String> routes) {
        public Snapshot {
            if (version < 0) throw new IllegalArgumentException("版本不能为负");
            routes = List.copyOf(routes);
        }
    }

    private volatile Snapshot current = new Snapshot(0, List.of());
    private final AtomicInteger accepted = new AtomicInteger();

    public void publish(Snapshot next) {
        // 答案开始：发布
        current = Objects.requireNonNull(next, "配置不能为空");
        // 答案结束：发布
    }

    public Snapshot current() {
        return current;
    }

    public int accept() {
        // 答案开始：计数
        return accepted.incrementAndGet();
        // 答案结束：计数
    }

    public int accepted() {
        return accepted.get();
    }

    // 教学反例：栅栏刻意让两个读都发生在写之前，即使 value 是 volatile 也会丢更新。
    public static int forcedLostUpdate() throws Exception {
        class Box {
            volatile int value;
        }
        Box box = new Box();
        CyclicBarrier bothRead = new CyclicBarrier(2);
        ExecutorService pool = Executors.newFixedThreadPool(2);
        try {
            Callable<Void> increment =
                    () -> {
                        int old = box.value;
                        bothRead.await(2, TimeUnit.SECONDS);
                        box.value = old + 1;
                        return null;
                    };
            Future<Void> first = pool.submit(increment), second = pool.submit(increment);
            first.get(3, TimeUnit.SECONDS);
            second.get(3, TimeUnit.SECONDS);
            return box.value;
        } finally {
            pool.shutdownNow();
            if (!pool.awaitTermination(3, TimeUnit.SECONDS))
                throw new IllegalStateException("线程未退出");
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

### 1. 机制：为什么一个 volatile 引用比两个 volatile 字段容易维护配置一致性？

参考表达：两个字段可能来自不同更新。先构造不可变聚合，再单点替换，读者只获取一次。

### 2. 边界：record 是否深不可变？

参考表达：不是。其引用字段不能重新赋值，所引用对象仍可能可变。本例通过 List.copyOf 保存不可修改的元素引用；String 元素不可变，才满足当前深度。

### 3. 取舍：AtomicInteger 与 synchronized 选哪个？

参考表达：单变量原子更新适合前者；多个相关字段要共同维护不变量时，锁或不可变聚合CAS更直观。

### 4. 追问：十万次没见到重排说明线程安全吗？

参考表达：不能。测试覆盖的是一些执行，JMM约束的是所有允许执行。用规范证明发布，用压力工具收集补充观察。

## 独立迁移与完成标准

不看答案重新实现一种业务变体：保持本节安全不变量，增加一个明确的失败或关闭条件，并写最小测试击穿旧实现。回答“新增条件改变了哪个状态机、哪些等待者必须被通知、哪些完成信号可靠”。24小时后重写关键方法，记录是否需要提示。

完成条件：A全通过；机制、边界、证据、独立迁移各能给可检验说明。任何资源泄漏、静默丢任务、错误成功或不受限等待仍未解决则不完成。源代码仅用于合成实验数据，不对用户真实服务注入故障。
