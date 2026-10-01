# C01-01 · 集合选择、视图与不可变边界

## 企业场景与进入条件

报表需要首次ID顺序、任务分发需要FIFO、查找需要Map；容器不同，视图行为也不同。先修C00；120分钟。

## 合同、输入输出与修改范围

stableIds按首次出现去重；dispatch保留重复并FIFO。firstById首次值获胜。snapshot接受null元素、校验半开范围、复制结构并返回不可修改列表；元素自身不深复制。与Arrays.asList、List.of、subList、unmodifiable view做完整对照。

本题在独立完整工程中运行：src是实现与调用方，test是全部公开测试，common是本课程内的完整领域checkpoint。只改答案区，接口和测试合同不变；可在test补自己的回归。标准解始终直接可读，未隐藏测试或答案。

## 概念与ASCII图

```text
List订单 -> LinkedHashSet稳定去重
List订单 -> ArrayDeque先进先出
List订单 -> Map按ID索引
原集合 -> 视图（共享结构）
原集合 -> 拷贝（独立结构） -> 元素仍可能共享
```

## 分步使用与验证

运行路线先区分：以下./gradlew命令适用于带Wrapper的源码仓库课程目录。若从Academy官方ZIP导入，用本题Check、Usage main运行按钮或IDE Gradle工具窗口的对应任务；Academy2026.9官方ZIP实际会剔除Wrapper脚本和JAR，不能承诺导入目录的终端./gradlew可用。完整CLI学习仍保留，使用源码仓库路线。

1. 在本课程根设完整JDK21；运行./gradlew :c01-01-views-lab:run看真实调用，Windows改用gradlew.bat。
2. 打开下方完整调用端与test/CollectionViewsTest.java，预测正常、边界、异常结果。作者源码是标准解；学习者占位副本才是练习起点。
3. 填写src/labs/foundation/CollectionViews.java的作答区；每完成一个方法运行./gradlew :c01-01-views-lab:test，先看到最小失败，再修复，不删断言。
4. 新增一条与本页易错点不同的回归。工具缺失记INVALID_ENV，没运行记NOT_RUN，不能用静态解析代替真实运行。
5. 提交源码阅读/观察表与本页迁移练习。A为自动契约，O为解释/观察，R为真实源码，T为显式教学子集；A绿不代表O/R或独立掌握完成。

主线JDK21、Gradle8.10.2、JUnit5.11.4，无前端/Docker/外部服务。测试限定合成输入和临时目录，不访问真实业务数据。

## 完整调用示例

```java
package labs.foundation;

public final class CollectionViewsUsage {
    public static void main(String[] args) {
        var orders =
                java.util.List.of(
                        new Order("A", "甲", 1, Order.Status.PAID),
                        new Order("A", "甲", 2, Order.Status.PAID));
        System.out.println("稳定去重=" + CollectionViews.stableIds(orders));
        System.out.println("排队分发=" + CollectionViews.dispatch(orders));
    }
}
```

## 可选提示

<div class="hint" title="H1：合同与不变量">把正常、边界、异常与失败后状态分别列出，先判断哪条可见测试在区分它们。</div>
<div class="hint" title="H2：最小反例">先从本页机制解释找到一个两三项输入的反例，避免直接加随机压力掩盖错误。</div>
<div class="hint" title="H3：步骤定位">沿下面标准解的步骤检查第一次状态偏离，再决定改哪一段；答案无需先过题即可查看。</div>

## 标准解与逐步解释

[完整实现副本](solutions/CollectionViews.java.txt)。以下是同一源码的完整内容；common、辅助类、调用端和全部测试均公开。

```java
package labs.foundation;

import java.util.*;

public final class CollectionViews {
    private CollectionViews() {}

    public static List<String> stableIds(List<Order> orders) {
        // 作答开始
        Set<String> ids = new LinkedHashSet<>();
        for (Order order : orders) ids.add(Objects.requireNonNull(order).id());
        return List.copyOf(ids);
        // 作答结束
    }

    public static <T> List<T> snapshot(List<T> input, int from, int to) {
        // 作答开始
        Objects.checkFromToIndex(from, to, input.size());
        return Collections.unmodifiableList(new ArrayList<>(input.subList(from, to)));
        // 作答结束
    }

    public static List<String> dispatch(List<Order> orders) {
        Deque<Order> queue = new ArrayDeque<>(orders);
        List<String> ids = new ArrayList<>();
        while (!queue.isEmpty()) ids.add(queue.removeFirst().id());
        return ids;
    }

    public static Map<String, Order> firstById(List<Order> orders) {
        Map<String, Order> result = new LinkedHashMap<>();
        for (Order order : orders) result.putIfAbsent(order.id(), order);
        return result;
    }
}
```

1. LinkedHashSet表达唯一性+遭遇顺序，HashSet只承诺唯一性，不给输出顺序合同。
2. snapshot必须new ArrayList后再unmodifiable，直接包装subList仍引用原结构。null被本题允许，所以不能机械用List.copyOf代替。
3. Arrays.asList固定长度且后备数组共享，set可用而add不行；List.of不可修改且拒绝null；subList是区间视图，结构改动需遵守其合同。
4. 外层不可修改不代表StringBuilder元素不能变化，测试有明确反例。去重期望O(N)、快照O(范围长度)，FIFO单步通常摊还O(1)。

## 源码与证据

[OpenJDK21固定源文件](https://github.com/openjdk/jdk/blob/890adb6410dab4606a4f26a942aed02fb2f55387/src/java.base/share/classes/java/util/Collections.java)，tag jdk-21+35，commit 890adb6410dab4606a4f26a942aed02fb2f55387。符号：unmodifiableList；Arrays.asList；ArrayList.subList。

记录写入源、写入视图、结构修改的不同结果，不假设所有不可修改容器null策略一致。

R记录必须含版本/SHA、文件/符号、输入、关键状态、分支、反例与结论。当前补丁JDK的src.zip不是GA原件，动态证据必须分别标识，不能编造断点截图。[源码路线与证据模板](../../../docs/源码与评阅.md)说明如何核对。教学容器只实现已列子集，不称生产级框架。

## 面试问答与迁移

问：业务只需去重能随意换Set吗？答：先确认输出顺序、null和比较器语义。
问：unmodifiableList能当并发快照吗？答：不能，它可共享可变源；同步和复制是不同维度。
问：Queue适合随机下标查询吗？答：接口目标不匹配，先选操作合同再看实现。
迁移：让snapshot深复制可变订单项，并明确复制失败如何处理。

## 完成标准

关键A全部通过；解释、证据、迁移按[评阅标准](../../../docs/源码与评阅.md)至少达到能讲机制和边界。记录H0独立到H4完整答案、首次失败、修复原因，并在24小时后不看答案完成变式。不能用“看懂了/复制后全绿”代替独立掌握，也不承诺面试结果。
