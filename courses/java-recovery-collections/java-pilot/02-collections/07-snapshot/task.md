# 07 · subList 视图、快照与不可变

## 依赖与完整项目结构

本题依赖完整 JDK21、Gradle Wrapper8.10.2、JUnit Jupiter5.11.4 / Platform1.11.4。编译使用 --release21；无需为每题新建工程或单独安装Gradle。课程根README列出完整目录与环境步骤。

```text
07-snapshot/
+-- task.md                       # 题目、提示、源码讲解、标准答案
+-- task-info.yaml                # Academy 文件与占位区配置
+-- src/labs/Snapshots.java             # 你需要实现的公开接口
+-- src/labs/SnapshotsUsage.java        # 完整 main 调用端
+-- test/SnapshotsTest.java             # 完整契约测试，全部可见
+-- test/SnapshotsExamplesTest.java     # 可扩展的使用样例测试
```

预计 45 分钟。先独立写 15–20 分钟，再按需展开提示；完成后运行检查、口述设计、补一条自己的边界测试。

## 业务背景与目标

返回 input[from,to) 的结构不可变、与原列表结构独立的浅快照；允许空区间。不允许选中区间含 null，但区间之外的 null 不影响。非法下标（包括 from>to）抛 IndexOutOfBoundsException。null 输入抛 NullPointerException。元素对象不要求深拷贝。

## 示例

原列表 set/clear 后快照仍为旧序列；快照里的可变元素仍可改变

## 实作要求

只修改实现文件的答案占位区域，保留公开 API。可在可见的 SnapshotsExamplesTest.java 中补充自己的 @Test；所有测试代码均可见；参考样例不会代替完整契约测试。先把输入、输出、异常和是否修改状态写成小清单。先写直观正确实现，再讨论优化。编译通过不等于通过契约。

## 三阶提示

### 提示1

subList 返回的是视图，不是快照

### 提示2

unmodifiableList 包裹视图只限制通过包装器修改

### 提示3

List.copyOf 拷贝结构并拒绝 null；浅拷贝仍共享元素引用

## 源码伴读（固定版本）

打开 [OpenJDK 21 GA，jdk-21+35](https://github.com/openjdk/jdk/blob/jdk-21%2B35/src/java.base/share/classes/java/util/ArrayList.java)，使用 IDE 搜索相关方法。先预测行为，再从分支、字段和调用关系找证据。不能只背结论；记录“类/方法 → 条件 → 状态变化 → 与本题的差异”。

## 源码定位、实验与证据

- 精确定位：ArrayList.subList、SubList.root/parent/offset、SubList.checkForComodification
- 可复现实验：建立父列表和 subList；先 parent.set，再在独立的新样例里 parent.add；对比 List.copyOf(subList) 结果。
- 验收证据：分别记录“结构修改”与“元素替换”的区别；证明只读包装仍可能联动原列表，结构快照不等于元素深拷贝。

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
public final class SnapshotsUsage {
    private SnapshotsUsage() {}

    public static void main(String[] args) {
        var original = new ArrayList<>(List.of("a", "b", "c"));
        List<String> snapshot = Snapshots.range(original, 0, 2);
        original.set(0, "x");
        original.clear();
        System.out.println("原列表=" + original);
        System.out.println("结构快照=" + snapshot);
    }
}
```

期望输出：

```text
原列表=[]
结构快照=[a, b]
```

## 写代码、使用接口、验证结果

在课程根目录执行（普通学员副本初始失败是预期行为）：

```sh
./gradlew :java-pilot-02-collections-07-snapshot:test
./gradlew :java-pilot-02-collections-07-snapshot:run
```

1. 先读完整调用端和两份测试，列出正常路径、边界及异常
2. 自己填写答案区，先跑 test，再跑 run 对照上面的输出
3. 在 ExamplesTest 增加一个尚未覆盖的边界；解释为何预期如此
4. 有错误先判断是编译、契约、状态变更还是输出理解错误，再修改实现
5. 测试和调用端都正确后，按下面的源码机制口述，再与标准答案对照

## 核心原理与源码解释

```text
父列表 ----> 元素A、元素B、元素C
   |
 subList视图 ----> 仍引用父列表关系

List.copyOf ----> 新的列表结构 ----> 同一批元素对象
```

subList 只建立范围视图，不分配独立元素序列。父列表结构修改会使旧视图状态失效，而父列表元素替换也会反映在视图中。Collections.unmodifiableList 只禁止通过包装器修改，不能阻止底层列表通过别的引用变化。

List.copyOf 把选中元素放进结构独立、不可修改的列表，并拒绝其中的 null。这里的“独立”针对列表结构；如果元素是可变的 ArrayList，两个列表仍指向同一个元素实例。一次快照成本 O(k)，并不自动保证多线程并发修改时的原子一致性。

## 标准答案与逐步解析

以下是本题公开的完整标准答案。建议独立尝试后再对照；答案随课程提供，不依赖隐藏文件、外部教师目录或折叠渲染功能。不同写法只要满足契约与复杂度要求也可以。

```java
// 标准实现位于作者占位区；学员填写同一公开接口，题面末尾提供完整答案与解析。
package labs;
import java.util.*;
public final class Snapshots {
    private Snapshots() {}
    public static <T> List<T> range(List<T> input, int from, int to) {
        Objects.requireNonNull(input, "input");
        Objects.checkFromToIndex(from, to, input.size());
        return List.copyOf(input.subList(from, to));
    }
}
```

对照顺序：先看输入校验与异常，再看核心状态更新，再看返回值和是否泄漏可变视图；最后用完整契约测试逐项证明行为。本题另一种正确写法及错误变体用于作者质量回归，不是对学员实现风格的强制要求。

## 面试题递进与参考表达

### 1. 机制：不可修改包装为什么不是快照？

参考表达：它仍委托底层集合，其他别名修改底层时内容会变化。

### 2. 边界：区间外有null要失败吗？

参考表达：不用；本题只要求选中区间不含null。

### 3. 取舍：为什么不深拷贝全部元素？

参考表达：泛型 API 不知道任意对象的复制语义与成本，必须由领域设计决定。

### 4. 追问：要跨线程发布一致快照呢？

参考表达：需要在受控锁或不可变状态更新机制下获取快照，并保证安全发布；copyOf 本身不是并发协议。
