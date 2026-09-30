# 06 · 聚合、Comparator 与确定性 Top-K

## 依赖与完整项目结构

本题依赖完整 JDK21、Gradle Wrapper8.10.2、JUnit Jupiter5.11.4 / Platform1.11.4。编译使用 --release21；无需为每题新建工程或单独安装Gradle。课程根README列出完整目录与环境步骤。

```text
06-top-words/
+-- task.md                       # 题目、提示、源码讲解、标准答案
+-- task-info.yaml                # Academy 文件与占位区配置
+-- src/labs/TopWords.java             # 你需要实现的公开接口
+-- src/labs/TopWordsUsage.java        # 完整 main 调用端
+-- test/TopWordsTest.java             # 完整契约测试，全部可见
+-- test/TopWordsExamplesTest.java     # 可扩展的使用样例测试
```

预计 50 分钟。先独立写 15–20 分钟，再按需展开提示；完成后运行检查、口述设计、补一条自己的边界测试。

## 业务背景与目标

输入已经分词：每个 token 使用 trim 后按 Locale.ROOT 小写，忽略空串；按次数降序，次数相同按 String 自然序升序，返回前 k 个新的可变 Count 列表。k<0 抛 IllegalArgumentException。输入/元素 null 抛 NullPointerException，k=0 也必须校验所有元素。不得修改输入。

## 示例

[b,a,b,c,a]，k=2 → [(a,2),(b,2)]

## 实作要求

只修改实现文件的答案占位区域，保留公开 API。可在可见的 TopWordsExamplesTest.java 中补充自己的 @Test；所有测试代码均可见；参考样例不会代替完整契约测试。先把输入、输出、异常和是否修改状态写成小清单。先写直观正确实现，再讨论优化。编译通过不等于通过契约。

## 三阶提示

### 提示1

先计数，再排序，再截取，分别写测试

### 提示2

不指定 Locale 的大小写转换可能受机器默认语言影响

### 提示3

比较器不要做计数相减并强转 int；给平票明确顺序

## 源码伴读（固定版本）

打开 [OpenJDK 21 GA，jdk-21+35](https://github.com/openjdk/jdk/blob/jdk-21%2B35/src/java.base/share/classes/java/util/Comparator.java)，使用 IDE 搜索相关方法。先预测行为，再从分支、字段和调用关系找证据。不能只背结论；记录“类/方法 → 条件 → 状态变化 → 与本题的差异”。

## 源码定位、实验与证据

- 精确定位：Comparator.comparingLong、reversed、thenComparing
- 可复现实验：用 b:2、a:2、c:3 比较两种排序键顺序；在测试中临时将默认 Locale 设为 tr-TR（最后恢复）。
- 验收证据：解释 reversed 放在整个链末尾与只反转计数排序的区别。补充一个平票反例；不要依赖 HashMap 当前碰巧的遍历顺序。

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
public final class TopWordsUsage {
    private TopWordsUsage() {}

    public static void main(String[] args) {
        List<String> tokens = List.of("b", "A", "b", "c", "a", " ");
        for (TopWords.Count item : TopWords.top(tokens, 2)) {
            System.out.println("词=" + item.word() + "，次数=" + item.count());
        }
    }
}
```

期望输出：

```text
词=a，次数=2
词=b，次数=2
```

## 写代码、使用接口、验证结果

在课程根目录执行（普通学员副本初始失败是预期行为）：

```sh
./gradlew :java-pilot-02-collections-06-top-words:test
./gradlew :java-pilot-02-collections-06-top-words:run
```

1. 先读完整调用端和两份测试，列出正常路径、边界及异常
2. 自己填写答案区，先跑 test，再跑 run 对照上面的输出
3. 在 ExamplesTest 增加一个尚未覆盖的边界；解释为何预期如此
4. 有错误先判断是编译、契约、状态变更还是输出理解错误，再修改实现
5. 测试和调用端都正确后，按下面的源码机制口述，再与标准答案对照

## 核心原理与源码解释

```text
token序列 --> 规范化 --> Map计数 --> 完整排序 --> 截取k项
                                     |
                              次数降序，词升序
```

聚合与排名分两步做。Locale.ROOT 保证规范化不受运行机器默认语言影响；否则同一输入在土耳其语环境中可能得到不同键。Comparator 先按计数降序，再对相同计数按词自然序排序，使结果不依赖 HashMap 的遍历偶然性。

对 n 个 token、m 个不同词，参考实现预期 O(n+m log m) 时间、O(m) 额外空间。计数比较使用 comparingLong，避免用差值强转 int 造成溢出或比较器不一致。k=0 仍校验全部输入，是题目明确选择的错误处理策略，而不是可以随便提前返回的优化机会。

## 标准答案与逐步解析

以下是本题公开的完整标准答案。建议独立尝试后再对照；答案随课程提供，不依赖隐藏文件、外部教师目录或折叠渲染功能。不同写法只要满足契约与复杂度要求也可以。

```java
// 标准实现位于作者占位区；学员填写同一公开接口，题面末尾提供完整答案与解析。
package labs;
import java.util.*;
public final class TopWords {
    public record Count(String word, long count) {}
    private TopWords() {}
    public static List<Count> top(List<String> tokens, int k) {
        Objects.requireNonNull(tokens, "tokens");
        if (k < 0) throw new IllegalArgumentException("negative k");
        Map<String, Long> counts = new HashMap<>();
        for (String token : tokens) {
            String word = Objects.requireNonNull(token, "token").trim().toLowerCase(Locale.ROOT);
            if (!word.isEmpty()) counts.merge(word, 1L, Long::sum);
        }
        List<Count> result = new ArrayList<>();
        counts.forEach((word, count) -> result.add(new Count(word, count)));
        result.sort(Comparator.comparingLong(Count::count).reversed().thenComparing(Count::word));
        return new ArrayList<>(result.subList(0, Math.min(k, result.size())));
    }
}
```

对照顺序：先看输入校验与异常，再看核心状态更新，再看返回值和是否泄漏可变视图；最后用完整契约测试逐项证明行为。本题另一种正确写法及错误变体用于作者质量回归，不是对学员实现风格的强制要求。

## 面试题递进与参考表达

### 1. 机制：为什么平票还要排序键？

参考表达：没有次级键，结果可能受容器遍历顺序影响，接口难以复现。

### 2. 边界：k比不同词数大怎么办？

参考表达：只返回实际存在的词，不补空值。

### 3. 取舍：小k、大m时如何改进？

参考表达：可用大小为k的堆，将排名阶段降到 O(m log k)，但必须仔细反转堆顶与平票规则。

### 4. 追问：无限日志流怎样算Top-K？

参考表达：先区分精确与近似、是否有时间窗口、是否能容忍延迟，再讨论分片聚合或近似计数。
