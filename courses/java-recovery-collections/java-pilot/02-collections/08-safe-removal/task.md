# 08 · Iterator 与安全原地删除

## 依赖与完整项目结构

本题使用完整 JDK21、Gradle8.10.2、JUnit Jupiter5.11.4 / Platform1.11.4，编译使用 --release21。源码仓库自带 Gradle Wrapper；Academy 导入课程由 IDE 管理 Gradle。无需为每题新建工程，具体入口见下面的运行说明。

```text
08-safe-removal/
+-- task.md                       # 题目、提示、源码讲解、标准答案
+-- task-info.yaml                # Academy 文件与占位区配置
+-- src/labs/SafeRemoval.java             # 你需要实现的公开接口
+-- src/labs/SafeRemovalUsage.java        # 完整 main 调用端
+-- test/SafeRemovalTest.java             # 完整契约测试，全部可见
+-- test/SafeRemovalExamplesTest.java     # 可扩展的使用样例测试
```

预计 45 分钟。先独立写 15–20 分钟，再按需展开提示；完成后运行检查、口述设计、补一条自己的边界测试。

## 业务背景与目标

对支持 Iterator.remove 的可变 List<Integer> 原地删除所有负数，保留其他元素顺序，返回删除数量。先完整校验 null 元素，非法输入失败后必须保持列表不变。不要求支持不可修改/定长列表。需用 Iterator，不能用索引删除或 removeIf 代替本题练习。

## 示例

[-1,-2,0,3,-4] → [0,3]，返回 3

## 实作要求

只修改实现文件的答案占位区域，保留公开 API。可在可见的 SafeRemovalExamplesTest.java 中补充自己的 @Test；所有测试代码均可见；参考样例不会代替完整契约测试。先把输入、输出、异常和是否修改状态写成小清单。先写直观正确实现，再讨论优化。编译通过不等于通过契约。

## 三阶提示

### 提示1

先做一遍校验再修改，保证本题要求的失败原子性

### 提示2

增强 for 本身背后也是迭代器，但不能随意 values.remove

### 提示3

让同一个 Iterator 执行 next 和 remove

## 源码伴读（固定版本）

打开 [OpenJDK 21 GA，jdk-21+35](https://github.com/openjdk/jdk/blob/jdk-21%2B35/src/java.base/share/classes/java/util/ArrayList.java)，使用 IDE 搜索相关方法。先预测行为，再从分支、字段和调用关系找证据。不能只背结论；记录“类/方法 → 条件 → 状态变化 → 与本题的差异”。

## 源码定位、实验与证据

- 精确定位：ArrayList.Itr.next/remove/checkForComodification、fastRemove、removeIf
- 可复现实验：对 [-1,-2,0] 逐次记录 cursor、lastRet、expectedModCount、modCount；比较 Iterator.remove 与列表直接 remove。
- 验收证据：指出 Iterator.remove 如何恢复游标和版本计数。再跟 fastRemove 的数组搬移；说明为何本题正确解对 ArrayList 最坏仍是二次复杂度。

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
public final class SafeRemovalUsage {
    private SafeRemovalUsage() {}

    public static void main(String[] args) {
        var values = new ArrayList<>(List.of(-1, -2, 0, 3, -4));
        int removed = SafeRemoval.removeNegative(values);
        System.out.println("删除数量=" + removed);
        System.out.println("剩余元素=" + values);
    }
}
```

期望输出：

```text
删除数量=3
剩余元素=[0, 3]
```

## 写代码、使用接口、验证结果

**Academy 导入或预览模式**：用题面底部的 **Check** 验证答案；打开 `src/labs/SafeRemovalUsage.java`，点击 `main` 旁的运行图标执行调用示例。也可在 Gradle 工具窗口选择本题模块的 `test` 或 `run` 任务。未完成 TODO 时，测试或调用失败是预期行为。

**源码仓库或普通 Gradle 学员副本模式**：仅在包含 `gradlew`、`gradlew.bat` 和 `gradle/wrapper/gradle-wrapper.jar` 的工程根目录执行下面命令。普通学员副本由 `authoring/materialize_learner.py` 生成。

实际验证的 Academy 官方导出 ZIP 和干净导入目录不包含上述三个 Wrapper 文件，不能直接在该导入目录执行 `./gradlew`。以下命令保留给源码与普通 Gradle 工程入口：

```sh
./gradlew :java-pilot-02-collections-08-safe-removal:test
./gradlew :java-pilot-02-collections-08-safe-removal:run
```

1. 先读完整调用端和两份测试，列出正常路径、边界及异常
2. 自己填写答案区；Academy 模式先点 Check 再运行 Usage，源码模式先跑 test 再跑 run，对照上面的输出
3. 在 ExamplesTest 增加一个尚未覆盖的边界；解释为何预期如此
4. 有错误先判断是编译、契约、状态变更还是输出理解错误，再修改实现
5. 测试和调用端都正确后，按下面的源码机制口述，再与标准答案对照

## 核心原理与源码解释

```text
迭代状态: cursor / lastRet / expectedModCount
next() --> 找到负数 --> 同一Iterator.remove()
                         |
                   更新游标与版本期望
```

Iterator 不只是一个下标，它维护当前遍历位置和上一次返回的位置。通过同一个迭代器 remove，容器实现会同步修正这些状态；直接调用列表 remove 却继续使用旧迭代器，可能触发 ConcurrentModificationException。这个 fail-fast 检查是尽力发现错误用法，不是线程安全保障。

本题先扫描 null，再进入删除阶段，因此输入校验失败不会半途删掉前面的元素。LinkedList 的迭代器删除可直接调整节点链接；ArrayList 每次删除仍要搬移后缀，所以整个删除过程最坏 O(n²)。正确删除方式与最高效批量删除方式是两个问题。

## 标准答案与逐步解析

以下是本题公开的完整标准答案。建议独立尝试后再对照；答案随课程提供，不依赖隐藏文件、外部教师目录或折叠渲染功能。不同写法只要满足契约与复杂度要求也可以。

```java
// 标准实现位于作者占位区；学员填写同一公开接口，题面末尾提供完整答案与解析。
package labs;
import java.util.*;
public final class SafeRemoval {
    private SafeRemoval() {}
    public static int removeNegative(List<Integer> values) {
        Objects.requireNonNull(values, "values");
        for (Integer value : values) Objects.requireNonNull(value, "element");
        int removed = 0;
        Iterator<Integer> it = values.iterator();
        while (it.hasNext()) {
            if (it.next() < 0) {
                it.remove();
                removed++;
            }
        }
        return removed;
    }
}
```

对照顺序：先看输入校验与异常，再看核心状态更新，再看返回值和是否泄漏可变视图；最后用完整契约测试逐项证明行为。本题另一种正确写法及错误变体用于作者质量回归，不是对学员实现风格的强制要求。

## 面试题递进与参考表达

### 1. 机制：增强for里直接remove为什么危险？

参考表达：增强for通常使用迭代器；结构变化绕过该迭代器的状态同步。

### 2. 边界：[-1,null,2] 应留下什么？

参考表达：完整原列表，因为本题约定校验失败前不做修改。

### 3. 取舍：ArrayList大量删除如何优化？

参考表达：可研究 removeIf 的标记/压缩策略；本题限定 Iterator 是为了先理解迭代协议。

### 4. 追问：线程安全列表就一定能这样删吗？

参考表达：仍要看迭代器语义；例如快照迭代器可能根本不支持remove，不能套用一个结论。
