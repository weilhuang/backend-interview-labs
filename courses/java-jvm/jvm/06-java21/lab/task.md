# C03-06 · Java21稳定特性与并发资源边界

## 企业场景与进入条件

订单事件类型增多后，分支遗漏和资源失控比语法冗长更危险。Java21稳定特性能让类型关系更清楚，但不会替代支付幂等、数据库连接预算或取消策略。预计150分钟。

## 可执行目标与合同

delta使用封闭Event的record pattern和pattern switch：Paid加金额、Refund减金额、Cancelled为0；null拒绝。newest接受SequencedCollection，按反向遭遇顺序取前count个并返回不可修改结构快照；count负数拒绝、超过元素数取全部；不改变输入，元素本身不深复制，允许源集合允许的null元素。

boundedSquares委托boundedMap执行，后者接收可控IntUnaryOperator供真实调用/测试观察虚拟线程。回调必须有界并响应中断，不可把任意无限阻塞交给本模型。至多64任务、并发许可1..8；结果按输入顺序；乘法溢出通过ExecutionException的cause传达；Future.get单项预算2秒，finally取消未完成项并关闭虚拟线程执行器。任务只有有界纯计算，此等待上限不等同任意生产阻塞调用可被强停。

分类：A为公开契约与资源回归；O为运行观察与解释；R为固定真实源码阅读；T为显式缩小的教学模型。测试通过不意味着O/R完成。JDK21为主线，Gradle8.10.2、JUnit5.11.4；无前端、无Docker、无真实业务数据。

## 机制图解

```text
事件 -> sealed穷尽分支 -> record分解 -> 金额变动
集合 -> reversed视图 -> 有限读取 -> 不可修改快照

最多64任务 -> 每任务虚拟线程 -> Semaphore(最多8)
                                    |
                                    v
                              受限业务资源 -> finally归还
```

## 编码与验证步骤

**Academy官方归档导入模式**：用本题Check检查作答，打开对应Usage.java的main运行按钮，或用IDE的Gradle工具窗口执行test/run。Academy2026.9官方导出实际会剔除gradlew、gradlew.bat与gradle-wrapper.jar，仅保留properties；不要在缺少Wrapper的导入目录照抄终端./gradlew命令。项目SDK与Gradle JVM均用完整JDK21。

**源码仓库或普通Gradle学员副本模式**：以下./gradlew命令针对含Wrapper的课程根，Windows用gradlew.bat。完整CLI与诊断教程保留；首次依赖解析失败应区分环境问题与作答失败。

1. 在课程根运行python scripts/lab.py doctor，确认完整JDK21。缺环境记INVALID_ENV，不判断知识水平。
2. 打开本题src与test全部文件，先运行调用端、读成功与失败样例。作者源码是完整解；学习者副本占位区才是待实现区域，答案也直接在本页下方。
3. 只修改答案区，保持公开合同。先运行本题测试，再补边界/异常测试；不要改掉断言消灭失败。
4. 课程根运行./gradlew :jvm-06-java21-lab:test 与 :jvm-06-java21-lab:run。Windows使用gradlew.bat。首次联网下载依赖与编码错误分开处理。
5. 观察入口：python scripts/lab.py usage。记录JDK完整版本、命令、输入、预期、实际和边界。新证据输出build/evidence，不覆盖此前结果。

## 完整调用示例

以下调用端文件、src下辅助类、test下所有测试均对学习者可见；没有隐藏评分逻辑。

```java
package labs.jvm;

public final class ModernOrdersUsage {
    public static void main(String[] args) throws Exception {
        System.out.println(
                "退款变动="
                        + ModernOrders.delta(
                                new ModernOrders.Refund("A", new ModernOrders.Money(40))));
        System.out.println(
                "最新事件="
                        + ModernOrders.newest(
                                new java.util.ArrayList<>(java.util.List.of("A", "B", "C")), 2));
        System.out.println("虚拟线程结果=" + ModernOrders.boundedSquares(java.util.List.of(2, 3), 2));
    }
}
```

## 渐进提示（可选，不锁答案）

<div class="hint" title="H1：先明确不变量">把合同拆为正常、边界、异常、清理四类，先找哪个可见测试证明当前机制。</div>
<div class="hint" title="H2：用最小反例">比较本题说明中的易错边界与完整测试；写一个能区分两种实现的最小输入。</div>
<div class="hint" title="H3：对照步骤">按下面标准解的逐步解释检查状态变化，先定位错误层，再决定是否重写。</div>

## 标准解与逐步解释

[可单独打开完整标准解](solutions/ModernOrders.java.txt)。同一实现也在这里完整展示，无须切分支、解锁或先通过题目。

```java
package labs.jvm;

import java.util.*;
import java.util.concurrent.*;

public final class ModernOrders {
    public record Money(long cents) {
        public Money {
            if (cents < 0) throw new IllegalArgumentException("金额非负");
        }
    }

    public sealed interface Event permits Paid, Refund, Cancelled {}

    public record Paid(String id, Money amount) implements Event {
        public Paid {
            Objects.requireNonNull(id);
            Objects.requireNonNull(amount);
        }
    }

    public record Refund(String id, Money amount) implements Event {
        public Refund {
            Objects.requireNonNull(id);
            Objects.requireNonNull(amount);
        }
    }

    public record Cancelled(String id) implements Event {
        public Cancelled {
            Objects.requireNonNull(id);
        }
    }

    private ModernOrders() {}

    public static long delta(Event event) {
        // 作答开始
        return switch (Objects.requireNonNull(event)) {
            case Paid(var id, Money(var cents)) -> cents;
            case Refund(var id, Money(var cents)) -> -cents;
            case Cancelled(var id) -> 0L;
        };
        // 作答结束
    }

    public static <T> List<T> newest(SequencedCollection<T> input, int count) {
        // 作答开始
        Objects.requireNonNull(input);
        if (count < 0) throw new IllegalArgumentException("数量不能为负");
        return input.reversed().stream().limit(count).toList();
        // 作答结束
    }

    public static List<Integer> boundedSquares(List<Integer> input, int maximum) throws Exception {
        return boundedMap(input, maximum, n -> Math.multiplyExact(n, n));
    }

    public static List<Integer> boundedMap(
            List<Integer> input, int maximum, java.util.function.IntUnaryOperator operation)
            throws Exception {
        // 作答开始
        Objects.requireNonNull(operation);
        Objects.requireNonNull(input);
        if (input.size() > 64 || maximum < 1 || maximum > 8)
            throw new IllegalArgumentException("超出任务预算");
        for (Integer n : input) Objects.requireNonNull(n);
        Semaphore permits = new Semaphore(maximum);
        try (var executor = Executors.newVirtualThreadPerTaskExecutor()) {
            List<Future<Integer>> futures = new ArrayList<>();
            for (int n : input)
                futures.add(
                        executor.submit(
                                () -> {
                                    permits.acquire();
                                    try {
                                        return operation.applyAsInt(n);
                                    } finally {
                                        permits.release();
                                    }
                                }));
            List<Integer> result = new ArrayList<>();
            try {
                for (var f : futures) result.add(f.get(2, TimeUnit.SECONDS));
            } finally {
                for (var f : futures) if (!f.isDone()) f.cancel(true);
            }
            return List.copyOf(result);
        }
        // 作答结束
    }
}
```

1. 先约束构造输入，避免嵌套record pattern遇到null内容造成意外不匹配。switch穷尽性覆盖已知sealed分支；业务上退款能否大于已付款仍要单独查账，不是语法替你解决。
2. reversed返回反向视图，修改可能映射到原集合；本题stream.toList生成不可修改快照，所以之后clear输入不影响结果。不能把SequencedCollection所有实现都想象为可修改，也不能把快照说成深不可变。
3. 一任务一虚拟线程；Semaphore限制正在使用稀缺资源的任务数，不通过池化虚拟线程达到限流。64的提交上限仍必要，否则等许可的线程和请求状态本身也消耗内存。
4. Future按输入收集保持顺序；失败会取消剩余任务。ExecutorService.close等待任务结束，若业务忽略中断仍可能卡住，因此本例任务受控，外部调用需自身超时。本课程诊断脚本另有进程看门狗。
5. JDK21中某些monitor/native阻塞可能pin载体；后续版本如JEP491改变monitor情形。没有观测到Pinned事件不能证明所有路径都不会pin，不把21结论无限延伸到25。
6. delta O(1)；newest O(min(N,count))空间同阶；任务总工作O(N)，保留O(N)，实际吞吐依赖CPU/下游。可接受替代是显式迭代反向视图并封装不可修改副本；不能直接返回原视图。

## 源码与证据

固定OpenJDK21 GA tag jdk-21+35，commit 890adb6410dab4606a4f26a942aed02fb2f55387。[真实源文件](https://github.com/openjdk/jdk/blob/890adb6410dab4606a4f26a942aed02fb2f55387/src/java.base/share/classes/java/util/SequencedCollection.java)；符号：SequencedCollection.reversed；ArrayList.reversed的视图实现。完整出处和补充规范见课程根[源码阅读清单](../../../docs/源码阅读清单.md)。

阅读接口遭遇顺序、可修改性与reverse视图合同，运行测试中的reversed().addFirst(3)观察原列表。虚拟线程另读VirtualThread.runContinuation及JEP444，记录版本，不猜测调度固定顺序。

R证据至少包含项目/版本/SHA、文件与符号、输入、关键分支、状态值、结论及反例。源码网页定位不等于已实际断点；本课程没有伪造截图。若IDE默认打开供应商补丁版源码，请另记录该版本，不冒充GA调试已完成。

## 面试问答与迁移

- 问：虚拟线程能加速CPU密集计算吗？答：它主要改善大量阻塞任务的可扩展性，不能创造CPU核心。平方只是确定性API示例，绝不是性能证明。
- 问：有虚拟线程为什么还要连接池？答：线程便宜不等于连接/文件句柄/服务端容量无限，必须有独立资源预算与准入。
- 问：pattern switch编译通过就没有分支风险？答：覆盖当前封闭类型层次不等于业务规则完整；新增事件版本、null内容、账本校验仍要设计。
- 问：为什么不统一使用Java21写所有面试题？答：目标环境可能只允许8/17。先明确编译器，表达同一算法与不变量；新语法用于降低噪音，不作为绕开兼容合同的理由。
- 迁移：把平方任务改成可控阻塞依赖，用latch证明最多maximum进入，取消后资源全归还；性能实验独立标O。

## 完成与复盘

A必须真正通过；O/R提交证据并按根目录[评阅标准](../../../docs/评阅标准.md)评阅。记录H0独立/H1-H4提示、首次失败、改动原因、24小时后换条件回测。至少能用一个反例解释结论边界。课程不以关键词计分，也不承诺面试结果。
