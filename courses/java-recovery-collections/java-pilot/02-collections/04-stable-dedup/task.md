# 04 · equals、hashCode 与稳定去重

## 依赖与完整项目结构

本题依赖完整 JDK21、Gradle Wrapper8.10.2、JUnit Jupiter5.11.4 / Platform1.11.4。编译使用 --release21；无需为每题新建工程或单独安装Gradle。课程根README列出完整目录与环境步骤。

```text
04-stable-dedup/
+-- task.md                       # 题目、提示、源码讲解、标准答案
+-- task-info.yaml                # Academy 文件与占位区配置
+-- src/labs/StableDedup.java             # 你需要实现的公开接口
+-- src/labs/StableDedupUsage.java        # 完整 main 调用端
+-- test/StableDedupTest.java             # 完整契约测试，全部可见
+-- test/StableDedupExamplesTest.java     # 可扩展的使用样例测试
```

预计 35 分钟。先独立写 15–20 分钟，再按需展开提示；完成后运行检查、口述设计、补一条自己的边界测试。

## 业务背景与目标

返回新的可变列表，按 equals 去重并保留首次出现顺序和首次对象实例。允许一个 null 元素；输入列表为 null 时抛 NullPointerException；不改动输入。元素须遵守 equals/hashCode 契约，调用期间不得修改身份字段。

## 示例

[z,a,null,a,z] → [z,a,null]

## 实作要求

只修改实现文件的答案占位区域，保留公开 API。可在可见的 StableDedupExamplesTest.java 中补充自己的 @Test；所有测试代码均可见；参考样例不会代替完整契约测试。先把输入、输出、异常和是否修改状态写成小清单。先写直观正确实现，再讨论优化。编译通过不等于通过契约。

## 三阶提示

### 提示1

查找性能、输出顺序、重复判断是三个独立问题

### 提示2

相同 hashCode 不等于相等；碰撞测试是必要的

### 提示3

如果返回 Set 的视图，是否满足新的可变 List 契约？

## 源码伴读（固定版本）

打开 [OpenJDK 21 GA，jdk-21+35](https://github.com/openjdk/jdk/blob/jdk-21%2B35/src/java.base/share/classes/java/util/LinkedHashSet.java)，使用 IDE 搜索相关方法。先预测行为，再从分支、字段和调用关系找证据。不能只背结论；记录“类/方法 → 条件 → 状态变化 → 与本题的差异”。

## 源码定位、实验与证据

- 精确定位：LinkedHashSet 构造器 → HashSet 包可见构造器 → LinkedHashMap
- 可复现实验：创建两个 equals 不等但 hashCode 相同的对象，重复插入其中一个；观察遍历顺序。
- 验收证据：画出“查重需要散列表，顺序需要链”的关系，并解释为什么碰撞不会把两个不等对象丢掉。

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
public final class StableDedupUsage {
    private StableDedupUsage() {}

    public static void main(String[] args) {
        List<String> values = Arrays.asList("z", "a", null, "a", "z");
        System.out.println("去重结果=" + StableDedup.distinct(values));
        System.out.println("原始列表=" + values);
    }
}
```

期望输出：

```text
去重结果=[z, a, null]
原始列表=[z, a, null, a, z]
```

## 写代码、使用接口、验证结果

在课程根目录执行（普通学员副本初始失败是预期行为）：

```sh
./gradlew :java-pilot-02-collections-04-stable-dedup:test
./gradlew :java-pilot-02-collections-04-stable-dedup:run
```

1. 先读完整调用端和两份测试，列出正常路径、边界及异常
2. 自己填写答案区，先跑 test，再跑 run 对照上面的输出
3. 在 ExamplesTest 增加一个尚未覆盖的边界；解释为何预期如此
4. 有错误先判断是编译、契约、状态变更还是输出理解错误，再修改实现
5. 测试和调用端都正确后，按下面的源码机制口述，再与标准答案对照

## 核心原理与源码解释

```text
输入: z -> a -> null -> a -> z
查重: 新   新    新     旧   旧
输出: z -> a -> null
```

去重不是“hashCode 相同就只留一个”。散列用于缩小搜索范围，最终仍通过 equals 判断身份。LinkedHashSet 使用带顺序信息的集合实现，使第一次成功插入建立输出顺序；再次插入相等元素不会替换第一份对象实例。

结果是新的 ArrayList，所以调用者增加或删除输出元素不会改变输入列表；但元素对象本身没有深拷贝。预期时间 O(n)，额外空间 O(k)。如果对象违反 equals/hashCode 契约，或者在集合中修改参与身份计算的字段，通用集合不能替你修复这一逻辑错误。

## 标准答案与逐步解析

以下是本题公开的完整标准答案。建议独立尝试后再对照；答案随课程提供，不依赖隐藏文件、外部教师目录或折叠渲染功能。不同写法只要满足契约与复杂度要求也可以。

```java
// 标准实现位于作者占位区；学员填写同一公开接口，题面末尾提供完整答案与解析。
package labs;
import java.util.*;
public final class StableDedup {
    private StableDedup() {}
    public static <T> List<T> distinct(List<T> input) {
        Objects.requireNonNull(input, "input");
        return new ArrayList<>(new LinkedHashSet<>(input));
    }
}
```

对照顺序：先看输入校验与异常，再看核心状态更新，再看返回值和是否泄漏可变视图；最后用完整契约测试逐项证明行为。本题另一种正确写法及错误变体用于作者质量回归，不是对学员实现风格的强制要求。

## 面试题递进与参考表达

### 1. 机制：hash 冲突会不会丢元素？

参考表达：不会，正确散列集合还会比较 equals。

### 2. 边界：两个相等但不同实例，保留哪一个？

参考表达：保留首次出现的实例；测试用 assertSame 验证。

### 3. 取舍：List.contains 循环可以吗？

参考表达：行为可正确，但通常会变成 O(n²)；大量数据下使用集合记录已见身份。

### 4. 追问：按用户ID去重却保留最新资料怎么做？

参考表达：先重新定义保留策略，再用 Map 的覆盖规则表达；那已不是本题的首次保留契约。
