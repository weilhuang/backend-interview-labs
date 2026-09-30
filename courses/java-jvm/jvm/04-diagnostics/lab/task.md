# C03-04 · CPU、锁、保留与池耗尽诊断

## 企业场景与进入条件

订单服务“慢”可能是CPU忙、监视器竞争、业务保留泄漏或池满。先按证据分类，再修复真正瓶颈。本节提供四个独立、12秒自动退出的事故进程以及可测修复。先修C02线程/锁/池；预计180分钟。

## 可执行目标与合同

ResourceGate最大并发1..8；业务异常、正常返回、等待中断后许可和active必须恢复，未获得许可的等待者不能release。保留原异常，调用方负责处理中断。

IncidentMain的cpu只单工作线程且每个计算块停10ms；lock有两个线程和受控释放；retention仅保留4MiB合成数组；pool仅2工作线程+2排队并明确拒绝第5任务。所有模式12秒清理。脚本看门狗24秒、堆96MiB、JFR16MiB，只接受模式不接受外部PID。默认不生成heap dump；可对retention显式--heap，先验证256MiB空闲磁盘。

分别运行python scripts/lab.py diagnose --mode cpu/lock/retention/pool（每次选一个）；收集后按diagnostics/事故档案模板.md写四份结论。

分类：A为公开契约与资源回归；O为运行观察与解释；R为固定真实源码阅读；T为显式缩小的教学模型。测试通过不意味着O/R完成。JDK21为主线，Gradle8.10.2、JUnit5.11.4；无前端、无Docker、无真实业务数据。

## 机制图解

```text
请求变慢
  |
  +-> CPU热点? -> JFR执行采样 + 多次线程快照
  +-> 锁等待?  -> 监视器地址 + owner/waiter + 调用栈
  +-> 堆增长?  -> 直方图 + 保留链 + 业务寿命
  +-> 池耗尽?  -> 活跃/队列/拒绝 + 下游等待

修复 -> 可见回归 -> 重新收集 -> 排除替代解释
```

## 编码与验证步骤

1. 在课程根运行python scripts/lab.py doctor，确认完整JDK21。缺环境记INVALID_ENV，不判断知识水平。
2. 打开本题src与test全部文件，先运行调用端、读成功与失败样例。作者源码是完整解；学习者副本占位区才是待实现区域，答案也直接在本页下方。
3. 只修改答案区，保持公开合同。先运行本题测试，再补边界/异常测试；不要改掉断言消灭失败。
4. 课程根运行./gradlew :jvm-04-diagnostics-lab:test 与 :jvm-04-diagnostics-lab:run。Windows使用gradlew.bat。首次联网下载依赖与编码错误分开处理。
5. 观察入口：python scripts/lab.py diagnose --mode cpu。记录JDK完整版本、命令、输入、预期、实际和边界。新证据输出build/evidence，不覆盖此前结果。

## 完整调用示例

以下调用端文件、src下辅助类、test下所有测试均对学习者可见；没有隐藏评分逻辑。

```java
package labs.jvm;

public final class ResourceGateUsage {
    public static void main(String[] args) throws Exception {
        var gate = new ResourceGate(2);
        System.out.println("业务结果=" + gate.call(() -> "订单完成"));
        System.out.println("剩余许可=" + gate.available());
    }
}
```

## 渐进提示（可选，不锁答案）

<div class="hint" title="H1：先明确不变量">把合同拆为正常、边界、异常、清理四类，先找哪个可见测试证明当前机制。</div>
<div class="hint" title="H2：用最小反例">比较本题说明中的易错边界与完整测试；写一个能区分两种实现的最小输入。</div>
<div class="hint" title="H3：对照步骤">按下面标准解的逐步解释检查状态变化，先定位错误层，再决定是否重写。</div>

## 标准解与逐步解释

[可单独打开完整标准解](solutions/ResourceGate.java.txt)。同一实现也在这里完整展示，无须切分支、解锁或先通过题目。

```java
package labs.jvm;

import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicInteger;

public final class ResourceGate {
    private final Semaphore permits;
    private final AtomicInteger active = new AtomicInteger();
    private final AtomicInteger peak = new AtomicInteger();

    public ResourceGate(int maximum) {
        if (maximum < 1 || maximum > 8) throw new IllegalArgumentException("并发限制须为1至8");
        permits = new Semaphore(maximum);
    }

    public <T> T call(Callable<T> action) throws Exception {
        // 作答开始
        java.util.Objects.requireNonNull(action, "业务操作不能为空");
        permits.acquire();
        try {
            int now = active.incrementAndGet();
            peak.accumulateAndGet(now, Math::max);
            try {
                return action.call();
            } finally {
                active.decrementAndGet();
            }
        } finally {
            permits.release();
        }
        // 作答结束
    }

    public int active() {
        return active.get();
    }

    public int peak() {
        return peak.get();
    }

    public int available() {
        return permits.availablePermits();
    }
}
```

1. acquire成功后才进入归还许可的finally，防止被中断等待者凭空增加可用配额。active的减少放在业务调用内部finally，业务抛异常也恢复。
2. peak记录并发高水位，读取是观察值；JUnit通过latch控制第一任务占用许可、第二任务取消，再释放和join，避免sleep猜调度。
3. DiagnosticRepairs展示四项修复：把计算改为有限预算；慢操作移到短临界区之外；保留容器按容量淘汰并最终clear；饱和池显式拒绝与有界shutdown。DiagnosticRepairsTest分别验证，不把“CPU变低”当自动断言。
4. Thread.print显示BLOCKED常与monitor有关；WAITING/TIMED_WAITING也可能是正常空闲。单次RUNNABLE不证明持续占满CPU。直方图只能给类型与数量，不能给根引用链；可选dump需另在分析器查看IncidentMain.retained保留路径。
5. Gate逻辑O(1)，阻塞等待时间依赖业务完成；生产还需要deadline、准入上限、指标、租户公平性。替代采用tryAcquire预算会改变API，应同时更新合同与测试。不要通过增加池线程数把下游压垮。

## 源码与证据

固定OpenJDK21 GA tag jdk-21+35，commit 890adb6410dab4606a4f26a942aed02fb2f55387。[真实源文件](https://github.com/openjdk/jdk/blob/890adb6410dab4606a4f26a942aed02fb2f55387/src/java.base/share/classes/java/util/concurrent/ThreadPoolExecutor.java)；符号：ThreadPoolExecutor.execute、addWorker、getTask、processWorkerExit。完整出处和补充规范见课程根[源码阅读清单](../../../docs/源码阅读清单.md)。

execute三个阶段：不足core尝试新worker；否则尝试入队并二次检查运行状态；入队失败再尝试非核心worker，失败则拒绝。输入第1..5个任务，记录worker数2、队列容量2、拒绝发生在哪个分支；本课不是生产线程池实现。

R证据至少包含项目/版本/SHA、文件与符号、输入、关键分支、状态值、结论及反例。源码网页定位不等于已实际断点；本课程没有伪造截图。若IDE默认打开供应商补丁版源码，请另记录该版本，不冒充GA调试已完成。

## 面试问答与迁移

- 问：发现大量WAITING就是死锁吗？答：不是。先找等待关系是否形成环，区分Condition、队列空闲和锁依赖。lock模式只有一条持锁等待链，最终受控释放，不称为永久死锁。
- 问：直方图byte[]最多意味着泄漏吗？答：不够。它可能是合法缓存或暂态批量；必须证明业务寿命结束而根仍可达。heap dump可能触发停顿/GC且含敏感数据，所以仅用合成隔离进程。
- 问：CPU利用率高怎么定位到Java方法？答：时间窗内采样热点并关联线程栈；单条栈只表示当时位置。JFR采样事件可能缺失，缺样本就说明不足而非编造热点百分比。
- 问：队列满该丢弃、阻塞还是拒绝？答：取决于业务可丢失性、调用方重试预算和延迟SLA；本课选择可见拒绝，不能静默丢单。追问重试风暴如何放大？无退避无幂等会增加压力与重复效果。
- 迁移：把等待业务改成抛异常/被中断，分别重新采集；证明每条资源链都有退出路径并补回归。

## 完成与复盘

A必须真正通过；O/R提交证据并按根目录[评阅标准](../../../docs/评阅标准.md)评阅。记录H0独立/H1-H4提示、首次失败、改动原因、24小时后换条件回测。至少能用一个反例解释结论边界。课程不以关键词计分，也不承诺面试结果。
