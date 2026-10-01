# C00-04 · 泛型仓库、PECS与函数式转换

## 企业场景与进入条件

服务希望复用仓库接口，并把订单聚合从循环迁移到Stream，必须保持结果、稳定顺序和异常语义。先修泛型与集合基本操作；150分钟。

## 合同、输入输出与修改范围

Repository<K,V>类型安全，saveAll接受Iterable<? extends V>，copyInto接受Collection<? super V>；对象和key非null，单批/仓库最多4096唯一键。先完整校验再提交，非法批次不能部分写入。find用Optional表达缺失。聚合只统计PAID并精确加法；相同金额稳定排序保持遭遇顺序。

本题在独立完整工程中运行：src是实现与调用方，test是全部公开测试，common是本课程内的完整领域checkpoint。只改答案区，接口和测试合同不变；可在test补自己的回归。标准解始终直接可读，未隐藏测试或答案。

## 概念与ASCII图

```text
来源 extends V -> 仓库<V> -> 目标 super V
                          |
                          +-> Optional<V> 缺失边界
订单 -> 过滤PAID -> 分组/精确求和 -> TreeMap稳定键顺序
                 循环与Stream必须同合同
```

## 分步使用与验证

运行路线先区分：以下./gradlew命令适用于带Wrapper的源码仓库课程目录。若从Academy官方ZIP导入，用本题Check、Usage main运行按钮或IDE Gradle工具窗口的对应任务；Academy2026.9官方ZIP实际会剔除Wrapper脚本和JAR，不能承诺导入目录的终端./gradlew可用。完整CLI学习仍保留，使用源码仓库路线。

1. 在本课程根设完整JDK21；运行./gradlew :c00-04-generics-lab:run看真实调用，Windows改用gradlew.bat。
2. 打开下方完整调用端与test/RepositoriesTest.java，预测正常、边界、异常结果。作者源码是标准解；学习者占位副本才是练习起点。
3. 填写src/labs/foundation/Repositories.java的作答区；每完成一个方法运行./gradlew :c00-04-generics-lab:test，先看到最小失败，再修复，不删断言。
4. 新增一条与本页易错点不同的回归。工具缺失记INVALID_ENV，没运行记NOT_RUN，不能用静态解析代替真实运行。
5. 提交源码阅读/观察表与本页迁移练习。A为自动契约，O为解释/观察，R为真实源码，T为显式教学子集；A绿不代表O/R或独立掌握完成。

主线JDK21、Gradle8.10.2、JUnit5.11.4，无前端/Docker/外部服务。测试限定合成输入和临时目录，不访问真实业务数据。

## 完整调用示例

```java
package labs.foundation;

public final class RepositoriesUsage {
    public static void main(String[] args) {
        var repo = new Repositories.MemoryRepository<String, Order>(Order::id);
        repo.saveAll(java.util.List.of(new Order("A", "甲", 200, Order.Status.PAID)));
        System.out.println("查找=" + repo.find("A"));
        System.out.println(
                "汇总=" + Repositories.streamTotals(java.util.List.of(repo.find("A").orElseThrow())));
    }
}
```

## 可选提示

<div class="hint" title="H1：合同与不变量">把正常、边界、异常与失败后状态分别列出，先判断哪条可见测试在区分它们。</div>
<div class="hint" title="H2：最小反例">先从本页机制解释找到一个两三项输入的反例，避免直接加随机压力掩盖错误。</div>
<div class="hint" title="H3：步骤定位">沿下面标准解的步骤检查第一次状态偏离，再决定改哪一段；答案无需先过题即可查看。</div>

## 标准解与逐步解释

[完整实现副本](solutions/Repositories.java.txt)。以下是同一源码的完整内容；common、辅助类、调用端和全部测试均公开。

```java
package labs.foundation;

import java.util.*;
import java.util.function.*;
import java.util.stream.*;

public final class Repositories {
    private Repositories() {}

    public interface Repository<K, V> {
        Optional<V> find(K key);

        void saveAll(Iterable<? extends V> values);

        void copyInto(Collection<? super V> target);
    }

    public static final class MemoryRepository<K, V> implements Repository<K, V> {
        private final Function<? super V, ? extends K> keyOf;
        private final Map<K, V> data = new LinkedHashMap<>();

        public MemoryRepository(Function<? super V, ? extends K> keyOf) {
            this.keyOf = Objects.requireNonNull(keyOf);
        }

        public Optional<V> find(K key) {
            return Optional.ofNullable(data.get(Objects.requireNonNull(key)));
        }

        public void saveAll(Iterable<? extends V> values) {
            // 作答开始
            Map<K, V> staged = new LinkedHashMap<>();
            for (V v : Objects.requireNonNull(values)) {
                Objects.requireNonNull(v);
                staged.put(Objects.requireNonNull(keyOf.apply(v)), v);
                if (staged.size() > 4096) throw new IllegalArgumentException("批次超限");
            }
            Set<K> keys = new HashSet<>(data.keySet());
            keys.addAll(staged.keySet());
            if (keys.size() > 4096) throw new IllegalStateException("仓库最多4096项");
            data.putAll(staged);
            // 作答结束
        }

        public void copyInto(Collection<? super V> target) {
            Objects.requireNonNull(target).addAll(data.values());
        }
    }

    public static Map<String, Long> loopTotals(List<Order> orders) {
        Map<String, Long> result = new TreeMap<>();
        for (Order o : orders)
            if (o.status() == Order.Status.PAID)
                result.merge(o.customer(), o.cents(), Math::addExact);
        return result;
    }

    public static Map<String, Long> streamTotals(List<Order> orders) {
        // 作答开始
        return orders.stream()
                .filter(o -> o.status() == Order.Status.PAID)
                .collect(
                        Collectors.toMap(
                                Order::customer, Order::cents, Math::addExact, TreeMap::new));
        // 作答结束
    }

    public static List<Order> stableByAmount(List<Order> orders) {
        return orders.stream().sorted(Comparator.comparingLong(Order::cents)).toList();
    }
}
```

1. PECS描述读取生产者与写入消费者：从extends中安全读为V，向super中安全写V，但不能反过来随意读成V。
2. staging局部Map先收集、校验key，再putAll，防止前两项写进去、第三项null抛错后留下半批。重复键覆盖在同一批中明确为最后值；仓库插入顺序保留键首次出现位置。
3. Stream的中间操作惰性，测试用filter计数器观察终止前0次、终止后2次。不要用count搭配peek就断言peek必执行，某些管线可优化。
4. reduce/merge使用Math.addExact维持溢出合同。TreeMap提供输出排序，但构造分组成本O(N log U)，不能套用HashMap的平均复杂度。
5. loopTotals是可接受替代；Optional适合返回缺失，不是所有字段和参数都套Optional。

## 源码与证据

[OpenJDK21固定源文件](https://github.com/openjdk/jdk/blob/890adb6410dab4606a4f26a942aed02fb2f55387/src/java.base/share/classes/java/util/stream/ReferencePipeline.java)，tag jdk-21+35，commit 890adb6410dab4606a4f26a942aed02fb2f55387。符号：filter、sorted、collect；Optional.map/orElseGet。

先记录何时构造管线、何时遍历；不要把教学仓库当数据库事务或并发安全仓库。

R记录必须含版本/SHA、文件/符号、输入、关键状态、分支、反例与结论。当前补丁JDK的src.zip不是GA原件，动态证据必须分别标识，不能编造断点截图。[源码路线与证据模板](../../../docs/源码与评阅.md)说明如何核对。教学容器只实现已列子集，不称生产级框架。

## 面试问答与迁移

问：List<Integer>能赋给List<Number>吗？答：不能，泛型不协变；但可读为List<? extends Number>。
问：Stream是并行的吗？答：默认不是；parallel还会引入结合律、共享副作用与线程池问题。
问：比较器只按金额排序，相等项顺序呢？答：本题有序流稳定排序保持遭遇顺序，但换数据源必须明确顺序来源。
迁移：让保存批次返回更新/新增计数，并确保失败原子性，不偷改已有对象。

## 完成标准

关键A全部通过；解释、证据、迁移按[评阅标准](../../../docs/源码与评阅.md)至少达到能讲机制和边界。记录H0独立到H4完整答案、首次失败、修复原因，并在24小时后不看答案完成变式。不能用“看懂了/复制后全绿”代替独立掌握，也不承诺面试结果。
