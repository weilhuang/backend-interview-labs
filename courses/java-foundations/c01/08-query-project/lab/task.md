# C01-08 · 索引查询、缓存与TopK综合项目

## 企业场景与进入条件

把索引、LRU和TopK组合成订单查询项目，比较快查与内存/更新成本。先修C01全部；240分钟。

## 合同、输入输出与修改范围

构造时最多4096订单且ID唯一，输入结构与内部索引隔离；Order为不可变fixture。find返回Optional；query按客户和最低金额（含边界）过滤、按ID排序，结果不可修改。缓存容量1..16，空结果也缓存；重复命中更新LRU。topCustomers仅累计PAID，按总额降序/客户升序，k非负。类非线程安全，不支持动态更新。

本题在独立完整工程中运行：src是实现与调用方，test是全部公开测试，common是本课程内的完整领域checkpoint。只改答案区，接口和测试合同不变；可在test补自己的回归。标准解始终直接可读，未隐藏测试或答案。

## 概念与ASCII图

```text
订单快照 -> byId -> 精确查找
          -> byCustomer -> 条件过滤 -> ID排序 -> LRU<Query,结果>
          -> 客户总额 -> 有界堆 -> TopK
JMH: 先固定业务等价，再隔离冷查/热缓存/构建成本
```

## 分步使用与验证

运行路线先区分：以下./gradlew命令适用于带Wrapper的源码仓库课程目录。若从Academy官方ZIP导入，用本题Check、Usage main运行按钮或IDE Gradle工具窗口的对应任务；Academy2026.9官方ZIP实际会剔除Wrapper脚本和JAR，不能承诺导入目录的终端./gradlew可用。完整CLI学习仍保留，使用源码仓库路线。

1. 在本课程根设完整JDK21；运行./gradlew :c01-08-query-project-lab:run看真实调用，Windows改用gradlew.bat。
2. 打开下方完整调用端与test/IndexedOrdersTest.java，预测正常、边界、异常结果。作者源码是标准解；学习者占位副本才是练习起点。
3. 填写src/labs/foundation/IndexedOrders.java的作答区；每完成一个方法运行./gradlew :c01-08-query-project-lab:test，先看到最小失败，再修复，不删断言。
4. 新增一条与本页易错点不同的回归。工具缺失记INVALID_ENV，没运行记NOT_RUN，不能用静态解析代替真实运行。
5. 提交源码阅读/观察表与本页迁移练习。A为自动契约，O为解释/观察，R为真实源码，T为显式教学子集；A绿不代表O/R或独立掌握完成。

主线JDK21、Gradle8.10.2、JUnit5.11.4，无前端/Docker/外部服务。测试限定合成输入和临时目录，不访问真实业务数据。

## 完整调用示例

```java
package labs.foundation;

public final class IndexedOrdersUsage {
    public static void main(String[] args) {
        var index =
                new IndexedOrders(
                        java.util.List.of(
                                new Order("A", "甲", 120, Order.Status.PAID),
                                new Order("B", "乙", 200, Order.Status.PAID)),
                        2);
        System.out.println("查询=" + index.query("甲", 100));
        System.out.println("Top客户=" + index.topCustomers(1));
        index.query("甲", 100);
        System.out.println("缓存命中=" + index.hits());
    }
}
```

## 可选提示

<div class="hint" title="H1：合同与不变量">把正常、边界、异常与失败后状态分别列出，先判断哪条可见测试在区分它们。</div>
<div class="hint" title="H2：最小反例">先从本页机制解释找到一个两三项输入的反例，避免直接加随机压力掩盖错误。</div>
<div class="hint" title="H3：步骤定位">沿下面标准解的步骤检查第一次状态偏离，再决定改哪一段；答案无需先过题即可查看。</div>

## 标准解与逐步解释

[完整实现副本](solutions/IndexedOrders.java.txt)。以下是同一源码的完整内容；common、辅助类、调用端和全部测试均公开。

```java
package labs.foundation;

import java.util.*;

public final class IndexedOrders {
    public record Query(String customer, long minimum) {
        public Query {
            Objects.requireNonNull(customer);
            if (minimum < 0) throw new IllegalArgumentException("最低金额非负");
        }
    }

    private final Map<String, List<Order>> byCustomer;
    private final Map<String, Order> byId;
    private final LinkedHashMap<Query, List<Order>> cache = new LinkedHashMap<>(16, .75f, true);
    private final int capacity;
    private long hits, misses;

    public IndexedOrders(List<Order> orders, int capacity) {
        if (capacity < 1 || capacity > 16 || orders.size() > 4096)
            throw new IllegalArgumentException("缓存1至16、订单最多4096");
        this.capacity = capacity;
        Map<String, Order> ids = new HashMap<>();
        Map<String, List<Order>> customers = new HashMap<>();
        for (Order order : orders) {
            Objects.requireNonNull(order);
            if (ids.putIfAbsent(order.id(), order) != null)
                throw new IllegalArgumentException("订单ID重复");
            customers.computeIfAbsent(order.customer(), ignored -> new ArrayList<>()).add(order);
        }
        Map<String, List<Order>> frozen = new HashMap<>();
        customers.forEach((customer, list) -> frozen.put(customer, List.copyOf(list)));
        byCustomer = Map.copyOf(frozen);
        byId = Map.copyOf(ids);
    }

    public Optional<Order> find(String id) {
        return Optional.ofNullable(byId.get(Objects.requireNonNull(id)));
    }

    public List<Order> query(String customer, long minimum) {
        // 作答开始
        Query key = new Query(customer, minimum);
        List<Order> result = cache.get(key);
        if (result != null) {
            hits++;
            return result;
        }
        misses++;
        result =
                byCustomer.getOrDefault(customer, List.of()).stream()
                        .filter(o -> o.cents() >= minimum)
                        .sorted(Comparator.comparing(Order::id))
                        .toList();
        cache.put(key, result);
        if (cache.size() > capacity) cache.pollFirstEntry();
        return result;
        // 作答结束
    }

    public record CustomerTotal(String customer, long cents) {}

    public List<CustomerTotal> topCustomers(int k) {
        // 作答开始
        if (k < 0) throw new IllegalArgumentException("k非负");
        if (k == 0) return List.of();
        Comparator<CustomerTotal> worst =
                Comparator.comparingLong(CustomerTotal::cents)
                        .thenComparing(CustomerTotal::customer, Comparator.reverseOrder());
        PriorityQueue<CustomerTotal> heap = new PriorityQueue<>(worst);
        for (var entry : byCustomer.entrySet()) {
            long total = 0;
            for (Order o : entry.getValue())
                if (o.status() == Order.Status.PAID) total = Math.addExact(total, o.cents());
            heap.add(new CustomerTotal(entry.getKey(), total));
            if (heap.size() > k) heap.remove();
        }
        return heap.stream().sorted(worst.reversed()).toList();
        // 作答结束
    }

    public List<Query> cachedOldestFirst() {
        return List.copyOf(cache.keySet());
    }

    public long hits() {
        return hits;
    }

    public long misses() {
        return misses;
    }
}
```

1. 构造建立byId与客户分组，冻结列表与Map，避免源列表clear导致索引失真；重复ID立即拒绝。
2. Query把customer+minimum都作为不可变key，不能只按客户缓存而混用过滤条件。cache.get即更新访问顺序；空列表不等于null，能够正确缓存无结果查询。
3. miss才扫描客户子列表并排序，随后插入、超过容量淘汰最旧。统计hit/miss是可用诊断接口，不通过私有反射验收。
4. topCustomers准确处理PENDING与溢出。索引构建O(N)期望，单次查询O(M+R log R)，缓存命中可复用不可修改结果；这些分析来自操作数，不从毫秒数倒推。
5. benchmark提供完整JMH1.37源码与独立构建入口，默认不跑；设计区分轮转未命中与热命中。若依赖/运行未完成，状态NOT_RUN，不写虚构“快10倍”。

## 源码与证据

[OpenJDK21固定源文件](https://github.com/openjdk/jdk/blob/890adb6410dab4606a4f26a942aed02fb2f55387/src/java.base/share/classes/java/util/LinkedHashMap.java)，tag jdk-21+35，commit 890adb6410dab4606a4f26a942aed02fb2f55387。符号：afterNodeAccess、pollFirstEntry；HashMap索引；JMH官方示例。

提交数据规模、读写比例、键热度、预热/fork、结果一致性和限制；不能以一张柱状图取代理由。

R记录必须含版本/SHA、文件/符号、输入、关键状态、分支、反例与结论。当前补丁JDK的src.zip不是GA原件，动态证据必须分别标识，不能编造断点截图。[源码路线与证据模板](../../../docs/源码与评阅.md)说明如何核对。教学容器只实现已列子集，不称生产级框架。

## 面试问答与迁移

问：加索引只赚不亏吗？答：增加内存与构建/更新成本，本课不可变快照避开更新一致性但不能外推动态服务。
问：缓存键漏一个过滤字段会怎样？答：复用错误结果，测试让同客户不同minimum并存击穿。
问：JMH如何防止错误比较？答：同数据/合同/访问分布，预热、fork、消费结果，分开构建成本和查询；报告JDK/参数/置信信息与GC分配。
迁移：加入状态过滤并更新Query字段、索引与回归；设计动态更新时明确缓存失效边界。

## 完成标准

关键A全部通过；解释、证据、迁移按[评阅标准](../../../docs/源码与评阅.md)至少达到能讲机制和边界。记录H0独立到H4完整答案、首次失败、修复原因，并在24小时后不看答案完成变式。不能用“看懂了/复制后全绿”代替独立掌握，也不承诺面试结果。
