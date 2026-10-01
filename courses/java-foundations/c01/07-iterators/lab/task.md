# C01-07 · 安全迭代、快照与并发复合操作

## 企业场景与进入条件

并发边界入口先区分fail-fast、快照与弱一致，再实现最小原子复合操作。不是完整JUC替代课程。先修C01与线程基础；180分钟。

## 合同、输入输出与修改范围

removeNegatives使用支持删除的List，保留非负相对顺序，null元素拒绝。COW迭代器绑定创建时数组且不支持remove。CHM迭代弱一致，不要求必见/必不见并发新增。increment按单个key用compute原子累计，溢出失败保留旧值，所有key非null。

本题在独立完整工程中运行：src是实现与调用方，test是全部公开测试，common是本课程内的完整领域checkpoint。只改答案区，接口和测试合同不变；可在test补自己的回归。标准解始终直接可读，未隐藏测试或答案。

## 概念与ASCII图

```text
普通迭代器 -> 自己remove -> 更新迭代状态
COW迭代器 -> 旧数组快照；写入 -> 新数组
CHM迭代器 -> 弱一致观察（不是完整快照）
compute(key) -> 读旧值+写新值为单键原子动作
```

## 分步使用与验证

运行路线先区分：以下./gradlew命令适用于带Wrapper的源码仓库课程目录。若从Academy官方ZIP导入，用本题Check、Usage main运行按钮或IDE Gradle工具窗口的对应任务；Academy2026.9官方ZIP实际会剔除Wrapper脚本和JAR，不能承诺导入目录的终端./gradlew可用。完整CLI学习仍保留，使用源码仓库路线。

1. 在本课程根设完整JDK21；运行./gradlew :c01-07-iterators-lab:run看真实调用，Windows改用gradlew.bat。
2. 打开下方完整调用端与test/ConcurrentViewsTest.java，预测正常、边界、异常结果。作者源码是标准解；学习者占位副本才是练习起点。
3. 填写src/labs/foundation/ConcurrentViews.java的作答区；每完成一个方法运行./gradlew :c01-07-iterators-lab:test，先看到最小失败，再修复，不删断言。
4. 新增一条与本页易错点不同的回归。工具缺失记INVALID_ENV，没运行记NOT_RUN，不能用静态解析代替真实运行。
5. 提交源码阅读/观察表与本页迁移练习。A为自动契约，O为解释/观察，R为真实源码，T为显式教学子集；A绿不代表O/R或独立掌握完成。

主线JDK21、Gradle8.10.2、JUnit5.11.4，无前端/Docker/外部服务。测试限定合成输入和临时目录，不访问真实业务数据。

## 完整调用示例

```java
package labs.foundation;

public final class ConcurrentViewsUsage {
    public static void main(String[] args) {
        var counters = new java.util.concurrent.ConcurrentHashMap<String, Long>();
        ConcurrentViews.increment(counters, "A");
        ConcurrentViews.increment(counters, "A");
        System.out.println("原子累计=" + counters);
        var list = new java.util.ArrayList<>(java.util.List.of(-1, 2, -3));
        System.out.println("删除=" + ConcurrentViews.removeNegatives(list) + "，剩余=" + list);
    }
}
```

## 可选提示

<div class="hint" title="H1：合同与不变量">把正常、边界、异常与失败后状态分别列出，先判断哪条可见测试在区分它们。</div>
<div class="hint" title="H2：最小反例">先从本页机制解释找到一个两三项输入的反例，避免直接加随机压力掩盖错误。</div>
<div class="hint" title="H3：步骤定位">沿下面标准解的步骤检查第一次状态偏离，再决定改哪一段；答案无需先过题即可查看。</div>

## 标准解与逐步解释

[完整实现副本](solutions/ConcurrentViews.java.txt)。以下是同一源码的完整内容；common、辅助类、调用端和全部测试均公开。

```java
package labs.foundation;

import java.util.*;
import java.util.concurrent.*;

public final class ConcurrentViews {
    private ConcurrentViews() {}

    public static int removeNegatives(List<Integer> values) {
        // 作答开始
        int removed = 0;
        for (Iterator<Integer> it = values.iterator(); it.hasNext(); )
            if (Objects.requireNonNull(it.next()) < 0) {
                it.remove();
                removed++;
            }
        return removed;
        // 作答结束
    }

    public static void increment(ConcurrentHashMap<String, Long> counters, String key) {
        // 作答开始
        counters.compute(
                Objects.requireNonNull(key),
                (ignored, old) -> old == null ? 1L : Math.addExact(old, 1L));
        // 作答结束
    }

    public static <T> List<T> collect(Iterator<T> iterator) {
        List<T> values = new ArrayList<>();
        iterator.forEachRemaining(values::add);
        return List.copyOf(values);
    }
}
```

1. 遍历时用该迭代器remove，而不是结构上直接list.remove；fail-fast是尽力检测，不能作为线程安全机制，也不写“并发必抛CME”。
2. COW适合读多写少且允许旧视图的场景，写时复制O(N)并保留旧数组直到读者不再引用；快照仍共享元素。
3. CHM弱一致测试只检查已声明允许集合和最终状态，不固定调度先后。compute将单键读改写放入原子边界，普通get再put没有同样保证。
4. 四线程通过latch一起开始、Future.get有界等待、finally关闭，不用sleep赌竞态。最终计数是A，调度中间观察是O；单键原子不代表跨键扣库存事务。

## 源码与证据

[OpenJDK21固定源文件](https://github.com/openjdk/jdk/blob/890adb6410dab4606a4f26a942aed02fb2f55387/src/java.base/share/classes/java/util/concurrent/ConcurrentHashMap.java)，tag jdk-21+35，commit 890adb6410dab4606a4f26a942aed02fb2f55387。符号：compute；CopyOnWriteArrayList.COWIterator；ArrayList.Itr.remove。

对照快照字段、弱一致说明和原子回调路径，锁粒度/实现细节绑定21版本。

R记录必须含版本/SHA、文件/符号、输入、关键状态、分支、反例与结论。当前补丁JDK的src.zip不是GA原件，动态证据必须分别标识，不能编造断点截图。[源码路线与证据模板](../../../docs/源码与评阅.md)说明如何核对。教学容器只实现已列子集，不称生产级框架。

## 面试问答与迁移

问：CME能不能捕获后重试就线程安全？答：不行，检测尽力且此前操作可能已生效。
问：COW元素是可变对象时读者能看到变化吗？答：快照只固定数组结构，元素仍共享。
问：compute回调适合做网络IO吗？答：可能延长同步路径并放大竞争，还应避免递归更新；外部调用需单独设计。
迁移：做“扣库存并记账”两个键，说明为何需要更大原子边界，不能宣称两个compute构成事务。

## 完成标准

关键A全部通过；解释、证据、迁移按[评阅标准](../../../docs/源码与评阅.md)至少达到能讲机制和边界。记录H0独立到H4完整答案、首次失败、修复原因，并在24小时后不看答案完成变式。不能用“看懂了/复制后全绿”代替独立掌握，也不承诺面试结果。
