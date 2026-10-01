# C01-04 · 哈希键契约与拉链扩容模型

## 企业场景与进入条件

多租户索引遇到哈希碰撞和扩容必须仍能找到正确订单。先修equals/hashCode与数组链表；210分钟。

## 合同、输入输出与修改范围

教学MiniHashMap<K,V>使用拉链、允许null键和值，支持put/get/remove/containsKey/size；put重复键返回旧值且不增size。0.75阈值扩容，最多4096条目。键的equals/hashCode在入表后应稳定。无树化、并发、迭代器与序列化。

本题在独立完整工程中运行：src是实现与调用方，test是全部公开测试，common是本课程内的完整领域checkpoint。只改答案区，接口和测试合同不变；可在test补自己的回归。标准解始终直接可读，未隐藏测试或答案。

## 概念与ASCII图

```text
hash扰动 -> 与容量-1取模 -> 桶 -> 链节点 -> equals确认
扩容: 保存旧next -> 按新掩码迁移 -> 接到新桶
同hash不等于同key；get=null不等于不存在
```

## 分步使用与验证

运行路线先区分：以下./gradlew命令适用于带Wrapper的源码仓库课程目录。若从Academy官方ZIP导入，用本题Check、Usage main运行按钮或IDE Gradle工具窗口的对应任务；Academy2026.9官方ZIP实际会剔除Wrapper脚本和JAR，不能承诺导入目录的终端./gradlew可用。完整CLI学习仍保留，使用源码仓库路线。

1. 在本课程根设完整JDK21；运行./gradlew :c01-04-hash-map-lab:run看真实调用，Windows改用gradlew.bat。
2. 打开下方完整调用端与test/MiniHashMapTest.java，预测正常、边界、异常结果。作者源码是标准解；学习者占位副本才是练习起点。
3. 填写src/labs/foundation/MiniHashMap.java的作答区；每完成一个方法运行./gradlew :c01-04-hash-map-lab:test，先看到最小失败，再修复，不删断言。
4. 新增一条与本页易错点不同的回归。工具缺失记INVALID_ENV，没运行记NOT_RUN，不能用静态解析代替真实运行。
5. 提交源码阅读/观察表与本页迁移练习。A为自动契约，O为解释/观察，R为真实源码，T为显式教学子集；A绿不代表O/R或独立掌握完成。

主线JDK21、Gradle8.10.2、JUnit5.11.4，无前端/Docker/外部服务。测试限定合成输入和临时目录，不访问真实业务数据。

## 完整调用示例

```java
package labs.foundation;

public final class MiniHashMapUsage {
    public static void main(String[] args) {
        var map = new MiniHashMap<String, Integer>();
        map.put("A", 1);
        System.out.println("替换旧值=" + map.put("A", 2));
        map.put(null, 3);
        System.out.println("空键=" + map.get(null) + "，数量=" + map.size());
    }
}
```

## 可选提示

<div class="hint" title="H1：合同与不变量">把正常、边界、异常与失败后状态分别列出，先判断哪条可见测试在区分它们。</div>
<div class="hint" title="H2：最小反例">先从本页机制解释找到一个两三项输入的反例，避免直接加随机压力掩盖错误。</div>
<div class="hint" title="H3：步骤定位">沿下面标准解的步骤检查第一次状态偏离，再决定改哪一段；答案无需先过题即可查看。</div>

## 标准解与逐步解释

[完整实现副本](solutions/MiniHashMap.java.txt)。以下是同一源码的完整内容；common、辅助类、调用端和全部测试均公开。

```java
package labs.foundation;

import java.util.*;

/** 教学拉链哈希表；没有树化、迭代器、并发或序列化。 */
public final class MiniHashMap<K, V> {
    private static final class Entry<K, V> {
        final int hash;
        final K key;
        V value;
        Entry<K, V> next;

        Entry(int hash, K key, V value, Entry<K, V> next) {
            this.hash = hash;
            this.key = key;
            this.value = value;
            this.next = next;
        }
    }

    @SuppressWarnings("unchecked")
    private Entry<K, V>[] table = (Entry<K, V>[]) new Entry[4];

    private int size;

    private static int hash(Object key) {
        int h = Objects.hashCode(key);
        return h ^ (h >>> 16);
    }

    private Entry<K, V> find(Object key) {
        int h = hash(key);
        for (Entry<K, V> e = table[h & (table.length - 1)]; e != null; e = e.next)
            if (e.hash == h && Objects.equals(e.key, key)) return e;
        return null;
    }

    public int size() {
        return size;
    }

    public int capacity() {
        return table.length;
    }

    public V get(Object key) {
        Entry<K, V> e = find(key);
        return e == null ? null : e.value;
    }

    public boolean containsKey(Object key) {
        return find(key) != null;
    }

    public V put(K key, V value) {
        // 作答开始
        Entry<K, V> existing = find(key);
        if (existing != null) {
            V old = existing.value;
            existing.value = value;
            return old;
        }
        if (size == 4096) throw new IllegalStateException("最多4096条目");
        if (size + 1 > table.length * 3 / 4) resize();
        int h = hash(key), bucket = h & (table.length - 1);
        table[bucket] = new Entry<>(h, key, value, table[bucket]);
        size++;
        return null;
        // 作答结束
    }

    @SuppressWarnings("unchecked")
    private void resize() {
        Entry<K, V>[] next = (Entry<K, V>[]) new Entry[table.length * 2];
        for (Entry<K, V> head : table)
            for (Entry<K, V> e = head; e != null; ) {
                Entry<K, V> after = e.next;
                int index = e.hash & (next.length - 1);
                e.next = next[index];
                next[index] = e;
                e = after;
            }
        table = next;
    }

    public V remove(Object key) {
        // 作答开始
        int h = hash(key), bucket = h & (table.length - 1);
        Entry<K, V> previous = null;
        for (Entry<K, V> e = table[bucket]; e != null; e = e.next) {
            if (e.hash == h && Objects.equals(e.key, key)) {
                if (previous == null) table[bucket] = e.next;
                else previous.next = e.next;
                e.next = null;
                size--;
                return e.value;
            }
            previous = e;
        }
        return null;
        // 作答结束
    }

    public record TenantKey(String tenant, String id) {
        public TenantKey {
            Objects.requireNonNull(tenant);
            Objects.requireNonNull(id);
        }
    }
}
```

1. 缓存扰动hash并比较equals，避免只按hash把碰撞键覆盖；TenantKey用不可变record并拒绝null组件。
2. 更新路径先找已有节点，只有新增才检查容量并size++。null值通过containsKey区分与缺失，不能让get承担两种语义。
3. resize时先保存旧next，否则改链后失去剩余节点；目标索引用新容量掩码。扩容并不改变键的逻辑值。
4. mutable key反例说明键的hash改变后按新桶查询会失败，容器没有义务扫描所有旧桶找回。正常hash假设下平均O(1)，所有键碰撞时拉链可退化O(N)。
5. 替代尾插而非头插也接受，迭代顺序从未成为本题合同。

## 源码与证据

[OpenJDK21固定源文件](https://github.com/openjdk/jdk/blob/890adb6410dab4606a4f26a942aed02fb2f55387/src/java.base/share/classes/java/util/HashMap.java)，tag jdk-21+35，commit 890adb6410dab4606a4f26a942aed02fb2f55387。符号：hash、putVal、resize。

把真实低高位拆分优化与本题重新按新mask挂链比较；结论绑定版本，不能说源码等于教学实现。

R记录必须含版本/SHA、文件/符号、输入、关键状态、分支、反例与结论。当前补丁JDK的src.zip不是GA原件，动态证据必须分别标识，不能编造断点截图。[源码路线与证据模板](../../../docs/源码与评阅.md)说明如何核对。教学容器只实现已列子集，不称生产级框架。

## 面试问答与迁移

问：为什么容量取2的幂？答：可用掩码定位，但低位分布需要扰动辅助；不等于任意hash都均匀。
问：equals相等却hash不同会怎样？答：破坏Map查找契约，等价键可能落不同桶。
问：树化解决所有碰撞攻击吗？答：真实HashMap有条件与比较路径，教学模型没有实现树化，不能借名词忽略边界。
迁移：加入可见entry快照并定义顺序政策；保持迁移过程无丢失、无重复size。

## 完成标准

关键A全部通过；解释、证据、迁移按[评阅标准](../../../docs/源码与评阅.md)至少达到能讲机制和边界。记录H0独立到H4完整答案、首次失败、修复原因，并在24小时后不看答案完成变式。不能用“看懂了/复制后全绿”代替独立掌握，也不承诺面试结果。
