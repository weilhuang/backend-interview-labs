# 11 · 基于访问顺序的 LRU 缓存

## 依赖与完整项目结构

本题使用完整 JDK21、Gradle8.10.2、JUnit Jupiter5.11.4 / Platform1.11.4，编译使用 --release21。源码仓库自带 Gradle Wrapper；Academy 导入课程由 IDE 管理 Gradle。无需为每题新建工程，具体入口见下面的运行说明。

```text
11-lru-cache/
+-- task.md                       # 题目、提示、源码讲解、标准答案
+-- task-info.yaml                # Academy 文件与占位区配置
+-- src/labs/LruCache.java             # 你需要实现的公开接口
+-- src/labs/LruCacheUsage.java        # 完整 main 调用端
+-- test/LruCacheTest.java             # 完整契约测试，全部可见
+-- test/LruCacheExamplesTest.java     # 可扩展的使用样例测试
```

预计 60 分钟。先独立写 15–20 分钟，再按需展开提示；完成后运行检查、口述设计、补一条自己的边界测试。

## 业务背景与目标

有界单线程 LRU：成功 get 刷新访问顺序；put 新键或更新旧键都刷新。超容量淘汰最久未访问键。未命中不影响顺序；拒绝 null key/value，失败不能改变状态。keysLeastToMostRecent 返回不可修改、结构独立的键快照。capacity 必须 >0。

## 示例

put(a),put(b),get(a),put(c)，容量2 → 淘汰 b

## 实作要求

只修改实现文件的答案占位区域，保留公开 API。可在可见的 LruCacheExamplesTest.java 中补充自己的 @Test；所有测试代码均可见；参考样例不会代替完整契约测试。先把输入、输出、异常和是否修改状态写成小清单。先写直观正确实现，再讨论优化。编译通过不等于通过契约。

## 三阶提示

### 提示1

LinkedHashMap 有 insertion-order 和 access-order 两种模式

### 提示2

覆盖已有 key 不应误删额外元素

### 提示3

先校验完整输入，再 put，再判断是否超限

## 源码伴读（固定版本）

打开 [OpenJDK 21 GA，jdk-21+35](https://github.com/openjdk/jdk/blob/jdk-21%2B35/src/java.base/share/classes/java/util/LinkedHashMap.java)，使用 IDE 搜索相关方法。先预测行为，再从分支、字段和调用关系找证据。不能只背结论；记录“类/方法 → 条件 → 状态变化 → 与本题的差异”。

## 源码定位、实验与证据

- 精确定位：LinkedHashMap.get、afterNodeAccess、afterNodeInsertion、removeEldestEntry
- 可复现实验：在 accessOrder=true 的映射执行 put(a),put(b),get(a),get(missing),put(a,new)。观察 head、tail 和 modCount；再对照 accessOrder=false。
- 验收证据：用证据解释 get 为什么可能修改结构，以及 iterator 与访问刷新并用的风险。找出自动 removeEldestEntry 钩子和本题显式淘汰写法的差异。

固定源码 tag jdk-21+35 对应 commit 890adb6410dab4606a4f26a942aed02fb2f55387。本题固定源码为21 GA；若运行的是21的后续更新，调试器源码与字节码应匹配该更新版本。可以对照差异，但请分别记录源码tag和实际运行时补丁版本。

## 面试表达与复盘

回答以下问题，每项用代码或测试支撑：

1. 你的实现维护什么不变量？失败后会留下什么状态？
2. 时间/空间复杂度是什么？最坏与均摊/预期是否相同？
3. 哪个测试会击穿一个看似合理的错误实现？
4. 与 JDK 实现有哪些差异？如果并发访问会发生什么？

完成后记录：首次测试结果、用了第几阶提示、实际耗时、失败原因、24 小时后能否无提示重写。不要用“测试全绿”替代源码解释与口述验收。


## 完整调用示例

以下文件已经放在工程中，可直接打开或通过本题 run 任务执行：

```java
package labs;

import java.util.*;

// 完整调用端：先构造输入，再调用业务接口，最后打印可核对的结果。
public final class LruCacheUsage {
    private LruCacheUsage() {}

    public static void main(String[] args) {
        var cache = new LruCache<String, Integer>(2);
        cache.put("a", 1);
        cache.put("b", 2);
        cache.get("a");
        cache.put("c", 3);
        System.out.println("从最旧到最新=" + cache.keysLeastToMostRecent());
        System.out.println("读取已淘汰键=" + cache.get("b"));
    }
}
```

期望输出：

```text
从最旧到最新=[a, c]
读取已淘汰键=Optional.empty
```

## 写代码、使用接口、验证结果

**Academy 导入或预览模式**：用题面底部的 **Check** 验证答案；打开 `src/labs/LruCacheUsage.java`，点击 `main` 旁的运行图标执行调用示例。也可在 Gradle 工具窗口选择本题模块的 `test` 或 `run` 任务。未完成 TODO 时，测试或调用失败是预期行为。

**源码仓库或普通 Gradle 学员副本模式**：仅在包含 `gradlew`、`gradlew.bat` 和 `gradle/wrapper/gradle-wrapper.jar` 的工程根目录执行下面命令。普通学员副本由 `authoring/materialize_learner.py` 生成。

实际验证的 Academy 官方导出 ZIP 和干净导入目录不包含上述三个 Wrapper 文件，不能直接在该导入目录执行 `./gradlew`。以下命令保留给源码与普通 Gradle 工程入口：

```sh
./gradlew :java-pilot-04-capstone-11-lru-cache:test
./gradlew :java-pilot-04-capstone-11-lru-cache:run
```

1. 先读完整调用端和两份测试，列出正常路径、边界及异常
2. 自己填写答案区；Academy 模式先点 Check 再运行 Usage，源码模式先跑 test 再跑 run，对照上面的输出
3. 在 ExamplesTest 增加一个尚未覆盖的边界；解释为何预期如此
4. 有错误先判断是编译、契约、状态变更还是输出理解错误，再修改实现
5. 测试和调用端都正确后，按下面的源码机制口述，再与标准答案对照

## 核心原理与源码解释

```text
最久未访问                         最近访问
a <-------------------------------> b
get(a): b <-----------------------> a
put(c), 容量2: 淘汰b，留下 a <-----> c
```

LinkedHashMap 在散列表节点之外维护双向顺序链。accessOrder=true 时，成功 get 与已有键 put 会刷新链上的位置。这样查找仍可利用散列表，淘汰时从最旧一端取得键。未命中没有可移动节点，因此不影响顺序。

先验证 key 与 value，再写入，再判断 size 是否超容量，可以避免非法输入改变状态。覆盖旧键不增加 size，所以不能按“每次put都删一个”实现淘汰。快照用 List.copyOf，返回独立且不可修改的键顺序。预期 get/put O(1)，生成快照 O(n)；成功读取也会改链，因此这里不是可无锁并发使用的只读缓存。

## 标准答案与逐步解析

以下是本题公开的完整标准答案。建议独立尝试后再对照；答案随课程提供，不依赖隐藏文件、外部教师目录或折叠渲染功能。不同写法只要满足契约与复杂度要求也可以。

```java
// 标准实现位于作者占位区；学员填写同一公开接口，题面末尾提供完整答案与解析。
package labs;
import java.util.*;
public final class LruCache<K,V> {
    private final int capacity;
    private final LinkedHashMap<K,V> entries = new LinkedHashMap<>(16,0.75f,true);
    public LruCache(int capacity) {
        if (capacity <= 0) throw new IllegalArgumentException("capacity");
        this.capacity = capacity;
    }
    public Optional<V> get(K key) {
        return Optional.ofNullable(entries.get(Objects.requireNonNull(key, "key")));
    }
    public void put(K key, V value) {
        Objects.requireNonNull(key, "key");
        Objects.requireNonNull(value, "value");
        entries.put(key,value);
        if (entries.size() > capacity) {
            Iterator<K> oldest = entries.keySet().iterator();
            oldest.next();
            oldest.remove();
        }
    }
    public List<K> keysLeastToMostRecent() {
        return List.copyOf(entries.keySet());
    }
    public int size() { return entries.size(); }
}
```

对照顺序：先看输入校验与异常，再看核心状态更新，再看返回值和是否泄漏可变视图；最后用完整契约测试逐项证明行为。本题另一种正确写法及错误变体用于作者质量回归，不是对学员实现风格的强制要求。

## 面试题递进与参考表达

### 1. 机制：LRU与FIFO区别是什么？

参考表达：FIFO只看插入先后；LRU还会在访问时更新新旧程度。

### 2. 边界：覆盖已有键会不会淘汰其他键？

参考表达：只有写入后size超容量才淘汰，单纯覆盖不会增加条目数量。

### 3. 取舍：为什么不直接暴露keySet？

参考表达：那是活动视图，可能允许修改并随缓存变化，破坏快照契约。

### 4. 追问：生产缓存还缺什么？

参考表达：至少要考虑并发、加载合并、过期、统计、内存计量和失败策略；它们不是这个单线程练习自动具备的功能。
