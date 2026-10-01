# 09 · 手写动态数组与摊还分析

## 依赖与完整项目结构

本题使用完整 JDK21、Gradle8.10.2、JUnit Jupiter5.11.4 / Platform1.11.4，编译使用 --release21。源码仓库自带 Gradle Wrapper；Academy 导入课程由 IDE 管理 Gradle。无需为每题新建工程，具体入口见下面的运行说明。

```text
09-mini-array-list/
+-- task.md                       # 题目、提示、源码讲解、标准答案
+-- task-info.yaml                # Academy 文件与占位区配置
+-- src/labs/IntVector.java             # 你需要实现的公开接口
+-- src/labs/IntVectorUsage.java        # 完整 main 调用端
+-- test/IntVectorTest.java             # 完整契约测试，全部可见
+-- test/IntVectorExamplesTest.java     # 可扩展的使用样例测试
```

预计 60 分钟。先独立写 15–20 分钟，再按需展开提示；完成后运行检查、口述设计、补一条自己的边界测试。

## 业务背景与目标

不使用 Collection 做底层存储。数组初始容量 0，第一次扩至 1，之后容量翻倍；removeAt 保持顺序、不缩容、返回删掉的值。下标必须 0≤index<size，错误不改状态。容量翻倍溢出允许 ArithmeticException，内存不足遵循 JVM 错误；不要求模拟 JDK 最大数组长度。

## 示例

add(1..5) 容量依次 1,2,4,4,8；删中间元素需要左移

## 实作要求

只修改实现文件的答案占位区域，保留公开 API。可在可见的 IntVectorExamplesTest.java 中补充自己的 @Test；所有测试代码均可见；参考样例不会代替完整契约测试。先把输入、输出、异常和是否修改状态写成小清单。先写直观正确实现，再讨论优化。编译通过不等于通过契约。

## 三阶提示

### 提示1

size 是有效元素数，capacity 是数组长度

### 提示2

System.arraycopy 支持同一数组的重叠区域

### 提示3

先保留旧值，再移动，最后减 size

## 源码伴读（固定版本）

打开 [OpenJDK 21 GA，jdk-21+35](https://github.com/openjdk/jdk/blob/jdk-21%2B35/src/java.base/share/classes/java/util/ArrayList.java)，使用 IDE 搜索相关方法。先预测行为，再从分支、字段和调用关系找证据。不能只背结论；记录“类/方法 → 条件 → 状态变化 → 与本题的差异”。

## 源码定位、实验与证据

- 精确定位：ArrayList 构造器、add、grow；jdk.internal.util.ArraysSupport.newLength
- 可复现实验：用默认构造器连续加入 11 个元素；与本题 IntVector 连续加入 5 个元素对比。只使用调试器观察容量，不在自动测试中用非法反射。
- 验收证据：画出两套容量曲线，并用几何级数解释均摊时间。JDK 源码数组增长不是本题“始终翻倍”的策略；源码默认构造与 initialCapacity=0 的分支也要分清。

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
public final class IntVectorUsage {
    private IntVectorUsage() {}

    public static void main(String[] args) {
        var vector = new IntVector();
        for (int i = 1; i <= 5; i++) vector.add(i);
        System.out.println("删除值=" + vector.removeAt(1));
        System.out.println("首项=" + vector.get(0));
        System.out.println("有效元素=" + vector.size());
        System.out.println("容量=" + vector.capacity());
    }
}
```

期望输出：

```text
删除值=2
首项=1
有效元素=4
容量=8
```

## 写代码、使用接口、验证结果

**Academy 导入或预览模式**：用题面底部的 **Check** 验证答案；打开 `src/labs/IntVectorUsage.java`，点击 `main` 旁的运行图标执行调用示例。也可在 Gradle 工具窗口选择本题模块的 `test` 或 `run` 任务。未完成 TODO 时，测试或调用失败是预期行为。

**源码仓库或普通 Gradle 学员副本模式**：仅在包含 `gradlew`、`gradlew.bat` 和 `gradle/wrapper/gradle-wrapper.jar` 的工程根目录执行下面命令。普通学员副本由 `authoring/materialize_learner.py` 生成。

实际验证的 Academy 官方导出 ZIP 和干净导入目录不包含上述三个 Wrapper 文件，不能直接在该导入目录执行 `./gradlew`。以下命令保留给源码与普通 Gradle 工程入口：

```sh
./gradlew :java-pilot-03-internals-09-mini-array-list:test
./gradlew :java-pilot-03-internals-09-mini-array-list:run
```

1. 先读完整调用端和两份测试，列出正常路径、边界及异常
2. 自己填写答案区；Academy 模式先点 Check 再运行 Usage，源码模式先跑 test 再跑 run，对照上面的输出
3. 在 ExamplesTest 增加一个尚未覆盖的边界；解释为何预期如此
4. 有错误先判断是编译、契约、状态变更还是输出理解错误，再修改实现
5. 测试和调用端都正确后，按下面的源码机制口述，再与标准答案对照

## 核心原理与源码解释

```text
有效区             空闲区
[1][2][3][4]        size=4, capacity=4
        add(5)
[1][2][3][4][5][ ][ ][ ]  size=5, capacity=8

removeAt(1): [1][3][4][5][ ][ ][ ][ ]
```

动态数组把逻辑长度 size 与物理容量分开。只有写入位置达到数组长度时才扩容，避免每次追加都复制所有元素。本题选 2 倍增长：n 次追加中的总搬运小于线性倍数，所以追加均摊 O(1)；单次扩容仍是 O(n)，最坏延迟不能被“均摊”抹掉。

removeAt 必须先校验并保存旧值，再把后缀左移，最后缩小 size。System.arraycopy 支持同数组重叠区域；索引、长度差一位会在中间删除与随机模型测试中暴露。本题不缩容，换取少一些内存抖动；OpenJDK21 ArrayList 的默认容量和约1.5倍增长策略与本题不同。

## 标准答案与逐步解析

以下是本题公开的完整标准答案。建议独立尝试后再对照；答案随课程提供，不依赖隐藏文件、外部教师目录或折叠渲染功能。不同写法只要满足契约与复杂度要求也可以。

```java
// 标准实现位于作者占位区；学员填写同一公开接口，题面末尾提供完整答案与解析。
package labs;
import java.util.Arrays;
public final class IntVector {
    private int[] data = new int[0];
    private int size;
    public int size() { return size; }
    public int capacity() { return data.length; }
    public void add(int value) {
        if (size == data.length) data = Arrays.copyOf(data, data.length == 0 ? 1 : Math.multiplyExact(data.length, 2));
        data[size++] = value;
    }
    public int get(int index) { check(index); return data[index]; }
    public int removeAt(int index) {
        check(index);
        int old = data[index];
        System.arraycopy(data, index + 1, data, index, size - index - 1);
        data[--size] = 0;
        return old;
    }
    private void check(int index) {
        if (index < 0 || index >= size) throw new IndexOutOfBoundsException(index);
    }
}
```

对照顺序：先看输入校验与异常，再看核心状态更新，再看返回值和是否泄漏可变视图；最后用完整契约测试逐项证明行为。本题另一种正确写法及错误变体用于作者质量回归，不是对学员实现风格的强制要求。

## 面试题递进与参考表达

### 1. 机制：为什么size不等于capacity？

参考表达：容量预留空位以分摊未来追加成本，size仅表示有效元素。

### 2. 边界：删最后一项需要复制几个元素？

参考表达：0个；这正是 size-index-1 的边界。

### 3. 取舍：翻倍与1.5倍如何选？

参考表达：在扩容次数、复制成本、额外空闲内存和峰值内存之间权衡。

### 4. 追问：为什么删一项不立即缩容？

参考表达：频繁跨越边界会来回复制；若需要缩容，通常引入滞后阈值或显式操作。
