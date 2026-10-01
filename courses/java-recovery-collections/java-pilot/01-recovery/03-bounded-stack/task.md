# 03 · 泛型、异常与有界栈

## 依赖与完整项目结构

本题使用完整 JDK21、Gradle8.10.2、JUnit Jupiter5.11.4 / Platform1.11.4，编译使用 --release21。源码仓库自带 Gradle Wrapper；Academy 导入课程由 IDE 管理 Gradle。无需为每题新建工程，具体入口见下面的运行说明。

```text
03-bounded-stack/
+-- task.md                       # 题目、提示、源码讲解、标准答案
+-- task-info.yaml                # Academy 文件与占位区配置
+-- src/labs/BoundedStack.java             # 你需要实现的公开接口
+-- src/labs/BoundedStackUsage.java        # 完整 main 调用端
+-- test/BoundedStackTest.java             # 完整契约测试，全部可见
+-- test/BoundedStackExamplesTest.java     # 可扩展的使用样例测试
```

预计 40 分钟。先独立写 15–20 分钟，再按需展开提示；完成后运行检查、口述设计、补一条自己的边界测试。

## 业务背景与目标

实现 LIFO 栈；capacity 必须 >0。push 先拒绝 null，再检查是否已满；满栈抛 IllegalStateException，状态不变。空 pop/peek 返回 Optional.empty；peek 不删除。保留泛型，不使用 raw type，不使用旧 Stack 类。单线程练习，不承诺线程安全。

## 示例

push(a),push(b),peek(),pop(),pop() → b,b,a

## 实作要求

只修改实现文件的答案占位区域，保留公开 API。可在可见的 BoundedStackExamplesTest.java 中补充自己的 @Test；所有测试代码均可见；参考样例不会代替完整契约测试。先把输入、输出、异常和是否修改状态写成小清单。先写直观正确实现，再讨论优化。编译通过不等于通过契约。

## 三阶提示

### 提示1

Deque 同时能做队列和栈，先选清楚哪一端代表栈顶

### 提示2

pollFirst 与 removeFirst 的空容器行为不同

### 提示3

先检查再修改，失败操作应保持状态

## 源码伴读（固定版本）

打开 [OpenJDK 21 GA，jdk-21+35](https://github.com/openjdk/jdk/blob/jdk-21%2B35/src/java.base/share/classes/java/util/ArrayDeque.java)，使用 IDE 搜索相关方法。先预测行为，再从分支、字段和调用关系找证据。不能只背结论；记录“类/方法 → 条件 → 状态变化 → 与本题的差异”。

## 源码定位、实验与证据

- 精确定位：ArrayDeque.push、pop、pollFirst、peekFirst、addFirst
- 可复现实验：对空 deque 分别调用 pollFirst、peekFirst、pop；再 push 两个元素并观察顺序。
- 验收证据：写出元素为 null 为什么会与 poll/peek 的空信号冲突；沿 addFirst 跟到 grow，区分业务容量与底层数组容量。

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
public final class BoundedStackUsage {
    private BoundedStackUsage() {}

    public static void main(String[] args) {
        var stack = new BoundedStack<String>(2);
        stack.push("a");
        stack.push("b");
        System.out.println("查看栈顶=" + stack.peek());
        System.out.println("弹出栈顶=" + stack.pop());
        System.out.println("剩余数量=" + stack.size());
    }
}
```

期望输出：

```text
查看栈顶=Optional[b]
弹出栈顶=Optional[b]
剩余数量=1
```

## 写代码、使用接口、验证结果

**Academy 导入或预览模式**：用题面底部的 **Check** 验证答案；打开 `src/labs/BoundedStackUsage.java`，点击 `main` 旁的运行图标执行调用示例。也可在 Gradle 工具窗口选择本题模块的 `test` 或 `run` 任务。未完成 TODO 时，测试或调用失败是预期行为。

**源码仓库或普通 Gradle 学员副本模式**：仅在包含 `gradlew`、`gradlew.bat` 和 `gradle/wrapper/gradle-wrapper.jar` 的工程根目录执行下面命令。普通学员副本由 `authoring/materialize_learner.py` 生成。

实际验证的 Academy 官方导出 ZIP 和干净导入目录不包含上述三个 Wrapper 文件，不能直接在该导入目录执行 `./gradlew`。以下命令保留给源码与普通 Gradle 工程入口：

```sh
./gradlew :java-pilot-01-recovery-03-bounded-stack:test
./gradlew :java-pilot-01-recovery-03-bounded-stack:run
```

1. 先读完整调用端和两份测试，列出正常路径、边界及异常
2. 自己填写答案区；Academy 模式先点 Check 再运行 Usage，源码模式先跑 test 再跑 run，对照上面的输出
3. 在 ExamplesTest 增加一个尚未覆盖的边界；解释为何预期如此
4. 有错误先判断是编译、契约、状态变更还是输出理解错误，再修改实现
5. 测试和调用端都正确后，按下面的源码机制口述，再与标准答案对照

## 核心原理与源码解释

```text
栈顶 --> [b] [a] <-- 栈底
push(c): 先校验容量再放入
peek(): 看b，不移动
pop(): 取b，剩[a]
```

Deque 是双端队列接口。把同一端约定为栈顶后，push 与 pollFirst 就组成 LIFO。ArrayDeque 用环形数组保存元素，正常端点操作不需要像 ArrayList 头删那样搬移整个序列；满底层数组时仍需扩容，所以端点操作常用均摊 O(1) 描述。

业务 capacity 与底层数组长度不是同一个概念。我们只限制能放多少个元素，不保证底层恰好分配相同槽位。拒绝 null 让 Optional.empty 有唯一含义：栈为空。push 先校验 null 再判断满，确保失败类型也符合约定。

## 标准答案与逐步解析

以下是本题公开的完整标准答案。建议独立尝试后再对照；答案随课程提供，不依赖隐藏文件、外部教师目录或折叠渲染功能。不同写法只要满足契约与复杂度要求也可以。

```java
// 标准实现位于作者占位区；学员填写同一公开接口，题面末尾提供完整答案与解析。
package labs;
import java.util.*;
public final class BoundedStack<T> {
    private final int capacity;
    private final Deque<T> values = new ArrayDeque<>();
    public BoundedStack(int capacity) {
        if (capacity <= 0) throw new IllegalArgumentException("capacity");
        this.capacity = capacity;
    }
    public void push(T value) {
        Objects.requireNonNull(value, "value");
        if (values.size() == capacity) throw new IllegalStateException("full");
        values.push(value);
    }
    public Optional<T> pop() {
        return Optional.ofNullable(values.pollFirst());
    }
    public Optional<T> peek() {
        return Optional.ofNullable(values.peekFirst());
    }
    public int size() { return values.size(); }
}
```

对照顺序：先看输入校验与异常，再看核心状态更新，再看返回值和是否泄漏可变视图；最后用完整契约测试逐项证明行为。本题另一种正确写法及错误变体用于作者质量回归，不是对学员实现风格的强制要求。

## 面试题递进与参考表达

### 1. 机制：为什么不用 java.util.Stack？

参考表达：Deque 更直接表达现代栈操作，避免继承 Vector 带来的不必要接口。

### 2. 边界：满栈 push(null) 抛哪种异常？

参考表达：按照本题校验优先级抛 NullPointerException，且保留原状态。

### 3. 取舍：容量检查后 push 是否线程安全？

参考表达：不是；两个线程可能同时看到未满。复合操作需要共同的同步边界。

### 4. 追问：要阻塞等待容量该换什么？

参考表达：考虑 BlockingDeque 或专门的有界阻塞结构，同时定义超时、取消与中断语义。
