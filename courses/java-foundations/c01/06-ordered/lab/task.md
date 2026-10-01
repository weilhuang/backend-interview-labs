# C01-06 · TreeMap范围、堆TopK与访问顺序LRU

## 企业场景与进入条件

业务既需要金额范围，也需要最高金额订单和近期缓存。三者分别对应有序树、堆与访问顺序映射。先修集合选择；180分钟。

## 合同、输入输出与修改范围

priceRange采用[from,to)且from非负；相同金额保留输入顺序。topK按金额降序、ID升序，k负拒绝、0为空、超N取全部。Lru容量1..128，键值非null，get和覆盖都会更新访问顺序，超容量淘汰最旧。

本题在独立完整工程中运行：src是实现与调用方，test是全部公开测试，common是本课程内的完整领域checkpoint。只改答案区，接口和测试合同不变；可在test补自己的回归。标准解始终直接可读，未隐藏测试或答案。

## 概念与ASCII图

```text
TreeMap: 键排序 -> subMap半开范围
PriorityQueue: 堆顶=当前最差 -> 超k淘汰 -> 最后排序输出
LinkedHashMap(accessOrder=true): get -> 移到最新 -> 淘汰最旧
```

## 分步使用与验证

运行路线先区分：以下./gradlew命令适用于带Wrapper的源码仓库课程目录。若从Academy官方ZIP导入，用本题Check、Usage main运行按钮或IDE Gradle工具窗口的对应任务；Academy2026.9官方ZIP实际会剔除Wrapper脚本和JAR，不能承诺导入目录的终端./gradlew可用。完整CLI学习仍保留，使用源码仓库路线。

1. 在本课程根设完整JDK21；运行./gradlew :c01-06-ordered-lab:run看真实调用，Windows改用gradlew.bat。
2. 打开下方完整调用端与test/OrderedQueriesTest.java，预测正常、边界、异常结果。作者源码是标准解；学习者占位副本才是练习起点。
3. 填写src/labs/foundation/OrderedQueries.java的作答区；每完成一个方法运行./gradlew :c01-06-ordered-lab:test，先看到最小失败，再修复，不删断言。
4. 新增一条与本页易错点不同的回归。工具缺失记INVALID_ENV，没运行记NOT_RUN，不能用静态解析代替真实运行。
5. 提交源码阅读/观察表与本页迁移练习。A为自动契约，O为解释/观察，R为真实源码，T为显式教学子集；A绿不代表O/R或独立掌握完成。

主线JDK21、Gradle8.10.2、JUnit5.11.4，无前端/Docker/外部服务。测试限定合成输入和临时目录，不访问真实业务数据。

## 完整调用示例

```java
package labs.foundation;

public final class OrderedQueriesUsage {
    public static void main(String[] args) {
        var orders =
                java.util.List.of(
                        new Order("A", "甲", 100, Order.Status.PAID),
                        new Order("B", "乙", 300, Order.Status.PAID));
        System.out.println("最高金额=" + OrderedQueries.topK(orders, 1));
        System.out.println("范围=" + OrderedQueries.priceRange(orders, 100, 300));
    }
}
```

## 可选提示

<div class="hint" title="H1：合同与不变量">把正常、边界、异常与失败后状态分别列出，先判断哪条可见测试在区分它们。</div>
<div class="hint" title="H2：最小反例">先从本页机制解释找到一个两三项输入的反例，避免直接加随机压力掩盖错误。</div>
<div class="hint" title="H3：步骤定位">沿下面标准解的步骤检查第一次状态偏离，再决定改哪一段；答案无需先过题即可查看。</div>

## 标准解与逐步解释

[完整实现副本](solutions/OrderedQueries.java.txt)。以下是同一源码的完整内容；common、辅助类、调用端和全部测试均公开。

```java
package labs.foundation;

import java.util.*;

public final class OrderedQueries {
    private OrderedQueries() {}

    public static List<Order> priceRange(List<Order> orders, long from, long to) {
        if (from < 0 || to < from) throw new IllegalArgumentException("金额半开区间非法");
        NavigableMap<Long, List<Order>> index = new TreeMap<>();
        for (Order o : orders) index.computeIfAbsent(o.cents(), k -> new ArrayList<>()).add(o);
        return index.subMap(from, true, to, false).values().stream().flatMap(List::stream).toList();
    }

    public static List<Order> topK(List<Order> orders, int k) {
        // 作答开始
        if (k < 0) throw new IllegalArgumentException("k不能为负");
        if (k == 0) return List.of();
        Comparator<Order> worst =
                Comparator.comparingLong(Order::cents)
                        .thenComparing(Order::id, Comparator.reverseOrder());
        PriorityQueue<Order> heap = new PriorityQueue<>(worst);
        for (Order o : orders) {
            heap.add(o);
            if (heap.size() > k) heap.remove();
        }
        return heap.stream().sorted(worst.reversed()).toList();
        // 作答结束
    }

    public static final class Lru<K, V> {
        private final int capacity;
        private final LinkedHashMap<K, V> entries = new LinkedHashMap<>(16, .75f, true);

        public Lru(int capacity) {
            if (capacity < 1 || capacity > 128) throw new IllegalArgumentException("容量须为1至128");
            this.capacity = capacity;
        }

        public void put(K key, V value) {
            entries.put(Objects.requireNonNull(key), Objects.requireNonNull(value));
            if (entries.size() > capacity) entries.pollFirstEntry();
        }

        public Optional<V> get(K key) {
            return Optional.ofNullable(entries.get(Objects.requireNonNull(key)));
        }

        public List<K> oldestFirst() {
            return List.copyOf(entries.keySet());
        }
    }
}
```

1. TreeMap把金额分组到List，避免同价订单被Map单值覆盖。范围端点包含性显式给定，不能只看自然语言“之间”。
2. 堆比较器让最差项在顶：金额小更差，金额同则ID大更差。最后反向比较器排序，不能直接把heap.iterator当有序输出。
3. 不用(a-b)或强制int转换写比较器，极端long会溢出并破坏反对称/传递性。测试包含全组合比较器规律与Long.MAX_VALUE。
4. TopK O(N log min(k,N))加输出O(k log k)，完整排序替代O(N log N)也接受公共合同，但要诚实说明性能差异。LRU是单线程策略模型，不自动获得并发一致性。

## 源码与证据

[OpenJDK21固定源文件](https://github.com/openjdk/jdk/blob/890adb6410dab4606a4f26a942aed02fb2f55387/src/java.base/share/classes/java/util/PriorityQueue.java)，tag jdk-21+35，commit 890adb6410dab4606a4f26a942aed02fb2f55387。符号：offer、siftUp、poll、siftDown；TreeMap.getEntryUsingComparator；LinkedHashMap.afterNodeAccess。

读取容器维持的不变量，不能凭几次计时断言树比数组普遍更快。

R记录必须含版本/SHA、文件/符号、输入、关键状态、分支、反例与结论。当前补丁JDK的src.zip不是GA原件，动态证据必须分别标识，不能编造断点截图。[源码路线与证据模板](../../../docs/源码与评阅.md)说明如何核对。教学容器只实现已列子集，不称生产级框架。

## 面试问答与迁移

问：TreeMap比较器与equals不一致会怎样？答：比较为0的键在树里视为同键，可能与一般Map使用者预期冲突。
问：堆遍历不是有序为何仍能找topK？答：只依赖堆顶最差不变量，不要求所有位置全序。
问：LRU get是读操作吗？答：业务上读值，但accessOrder模式会改内部顺序，多线程分析不能当纯读。
迁移：缓存加TTL时同时规定过期与LRU谁先淘汰，使用假时钟测试，不sleep等过期。

## 完成标准

关键A全部通过；解释、证据、迁移按[评阅标准](../../../docs/源码与评阅.md)至少达到能讲机制和边界。记录H0独立到H4完整答案、首次失败、修复原因，并在24小时后不看答案完成变式。不能用“看懂了/复制后全绿”代替独立掌握，也不承诺面试结果。
