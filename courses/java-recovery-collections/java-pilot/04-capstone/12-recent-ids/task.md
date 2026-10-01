# 12 · 近期去重窗口：组合数据结构

## 依赖与完整项目结构

本题使用完整 JDK21、Gradle8.10.2、JUnit Jupiter5.11.4 / Platform1.11.4，编译使用 --release21。源码仓库自带 Gradle Wrapper；Academy 导入课程由 IDE 管理 Gradle。无需为每题新建工程，具体入口见下面的运行说明。

```text
12-recent-ids/
+-- task.md                       # 题目、提示、源码讲解、标准答案
+-- task-info.yaml                # Academy 文件与占位区配置
+-- src/labs/RecentIds.java             # 你需要实现的公开接口
+-- src/labs/RecentIdsUsage.java        # 完整 main 调用端
+-- test/RecentIdsTest.java             # 完整契约测试，全部可见
+-- test/RecentIdsExamplesTest.java     # 可扩展的使用样例测试
```

预计 65 分钟。先独立写 15–20 分钟，再按需展开提示；完成后运行检查、口述设计、补一条自己的边界测试。

## 业务背景与目标

单线程去重窗口只保留最近 capacity 个成功接受的不同 ID。窗口中重复 offer 返回 false 且不刷新顺序；新 ID 返回 true，已满时淘汰最早接受的 ID。被淘汰 ID 可再次接受。ID 区分大小写并保留原样，null/空白非法，失败不改状态；快照不可修改且独立。

## 示例

容量2：a,b,a,c,a 的接受结果 true,true,false,true,true

## 实作要求

只修改实现文件的答案占位区域，保留公开 API。可在可见的 RecentIdsExamplesTest.java 中补充自己的 @Test；所有测试代码均可见；参考样例不会代替完整契约测试。先把输入、输出、异常和是否修改状态写成小清单。先写直观正确实现，再讨论优化。编译通过不等于通过契约。

## 三阶提示

### 提示1

Deque 管顺序、Set 管快速存在性；每次修改后两者表示同一批 ID

### 提示2

重复检查必须在淘汰之前

### 提示3

讲清楚该窗口按“接受数量”计数，不是时间 TTL，也不是全局 exactly-once

## 源码伴读（固定版本）

打开 [OpenJDK 21 GA，jdk-21+35](https://github.com/openjdk/jdk/blob/jdk-21%2B35/src/java.base/share/classes/java/util/ArrayDeque.java)，使用 IDE 搜索相关方法。先预测行为，再从分支、字段和调用关系找证据。不能只背结论；记录“类/方法 → 条件 → 状态变化 → 与本题的差异”。

## 源码定位、实验与证据

- 精确定位：ArrayDeque.addLast/removeFirst/grow 与 HashSet.add/remove
- 可复现实验：按容量2执行 a,b,a,c,a，每步画队列和集合；再跟踪环形数组头尾移动，勿假定底层数组物理顺序等于逻辑顺序。
- 验收证据：写出重复请求为何不刷新、淘汰为何必须同步删除集合元素。构造“队列删除、集合忘删”的反例，再说明多线程下复合操作的竞态点。

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
public final class RecentIdsUsage {
    private RecentIdsUsage() {}

    public static void main(String[] args) {
        var window = new RecentIds(2);
        List<Boolean> accepted = new ArrayList<>();
        for (String id : List.of("a", "b", "a", "c", "a")) {
            accepted.add(window.offer(id));
        }
        System.out.println("接受结果=" + accepted);
        System.out.println("最终窗口=" + window.snapshot());
    }
}
```

期望输出：

```text
接受结果=[true, true, false, true, true]
最终窗口=[c, a]
```

## 写代码、使用接口、验证结果

**Academy 导入或预览模式**：用题面底部的 **Check** 验证答案；打开 `src/labs/RecentIdsUsage.java`，点击 `main` 旁的运行图标执行调用示例。也可在 Gradle 工具窗口选择本题模块的 `test` 或 `run` 任务。未完成 TODO 时，测试或调用失败是预期行为。

**源码仓库或普通 Gradle 学员副本模式**：仅在包含 `gradlew`、`gradlew.bat` 和 `gradle/wrapper/gradle-wrapper.jar` 的工程根目录执行下面命令。普通学员副本由 `authoring/materialize_learner.py` 生成。

实际验证的 Academy 官方导出 ZIP 和干净导入目录不包含上述三个 Wrapper 文件，不能直接在该导入目录执行 `./gradlew`。以下命令保留给源码与普通 Gradle 工程入口：

```sh
./gradlew :java-pilot-04-capstone-12-recent-ids:test
./gradlew :java-pilot-04-capstone-12-recent-ids:run
```

1. 先读完整调用端和两份测试，列出正常路径、边界及异常
2. 自己填写答案区；Academy 模式先点 Check 再运行 Usage，源码模式先跑 test 再跑 run，对照上面的输出
3. 在 ExamplesTest 增加一个尚未覆盖的边界；解释为何预期如此
4. 有错误先判断是编译、契约、状态变更还是输出理解错误，再修改实现
5. 测试和调用端都正确后，按下面的源码机制口述，再与标准答案对照

## 核心原理与源码解释

```text
队列order: [a,b]       集合seen: {a,b}
offer(a): 拒绝；两者不动
offer(c): 队列删a并加c；集合删a并加c
结果:      [b,c]                 {b,c}
```

队列负责最早接受顺序，集合负责预期O(1)判断是否已经出现。两者必须始终含有同一批ID，且 size 不超过容量。重复检查放在淘汰之前；否则重复请求也可能把窗口最旧记录删掉，改变后续去重语义。

这与LRU不同：重复请求不会刷新顺序，窗口按最近成功接受的不同ID数量定义，而不是按访问次数或时间定义。淘汰后再次出现可以重新接受，因此只能提供有限范围去重。服务重启、跨进程或无限时间的幂等需求要引入不同的持久化和事务设计。

## 标准答案与逐步解析

以下是本题公开的完整标准答案。建议独立尝试后再对照；答案随课程提供，不依赖隐藏文件、外部教师目录或折叠渲染功能。不同写法只要满足契约与复杂度要求也可以。

```java
// 标准实现位于作者占位区；学员填写同一公开接口，题面末尾提供完整答案与解析。
package labs;
import java.util.*;
public final class RecentIds {
    private final int capacity;
    private final Deque<String> order = new ArrayDeque<>();
    private final Set<String> seen = new HashSet<>();
    public RecentIds(int capacity) {
        if (capacity <= 0) throw new IllegalArgumentException("capacity");
        this.capacity = capacity;
    }
    public boolean offer(String id) {
        Objects.requireNonNull(id, "id");
        if (id.isBlank()) throw new IllegalArgumentException("blank id");
        if (seen.contains(id)) return false;
        if (order.size() == capacity) seen.remove(order.removeFirst());
        order.addLast(id);
        seen.add(id);
        return true;
    }
    public List<String> snapshot() {
        return List.copyOf(order);
    }
}
```

对照顺序：先看输入校验与异常，再看核心状态更新，再看返回值和是否泄漏可变视图；最后用完整契约测试逐项证明行为。本题另一种正确写法及错误变体用于作者质量回归，不是对学员实现风格的强制要求。

## 面试题递进与参考表达

### 1. 机制：为什么需要队列加集合？

参考表达：仅队列查重通常是线性扫描；仅集合又不能方便知道谁最早。

### 2. 边界：被淘汰的ID再来为什么接受？

参考表达：窗口只记住最近容量内的成功记录，永久去重并非本题承诺。

### 3. 取舍：为何重复不刷新？

参考表达：这是明确的业务语义，使窗口按接受顺序推进；若刷新就变成另一种策略。

### 4. 追问：用Redis做跨服务幂等够不够？

参考表达：还需定义幂等键、有效期、处理状态及与业务写入的原子边界，不能仅凭一个SETNX宣称exactly-once。
