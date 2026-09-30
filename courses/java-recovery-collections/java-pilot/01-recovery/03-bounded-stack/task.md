# 03 · 泛型、异常与有界栈

预计 40 分钟。先独立写 15–20 分钟，再按需展开提示；完成后运行检查、口述设计、补一条自己的边界测试。

## 业务背景与目标

实现 LIFO 栈；capacity 必须 >0。push 先拒绝 null，再检查是否已满；满栈抛 IllegalStateException，状态不变。空 pop/peek 返回 Optional.empty；peek 不删除。保留泛型，不使用 raw type，不使用旧 Stack 类。单线程练习，不承诺线程安全。

## 示例

push(a),push(b),peek(),pop(),pop() → b,b,a

## 实作要求

只修改实现文件的答案占位区域，保留公开 API。可在可见的 BoundedStackExamplesTest.java 中补充自己的 @Test；参考样例不会代替隐藏契约测试。先把输入、输出、异常和是否修改状态写成小清单。先写直观正确实现，再讨论优化。编译通过不等于通过契约。

## 三阶提示

<div class="hint" title="提示 1">
Deque 同时能做队列和栈，先选清楚哪一端代表栈顶
</div>

<div class="hint" title="提示 2">
pollFirst 与 removeFirst 的空容器行为不同
</div>

<div class="hint" title="提示 3">
先检查再修改，失败操作应保持状态
</div>

## 源码伴读（固定版本）

打开 [OpenJDK 17 GA，jdk-17+35](https://github.com/openjdk/jdk/blob/jdk-17%2B35/src/java.base/share/classes/java/util/ArrayDeque.java)，使用 IDE 搜索相关方法。先预测行为，再从分支、字段和调用关系找证据。不能只背结论；记录“类/方法 → 条件 → 状态变化 → 与本题的差异”。

## 源码定位、实验与证据

- 精确定位：ArrayDeque.push、pop、pollFirst、peekFirst、addFirst
- 可复现实验：对空 deque 分别调用 pollFirst、peekFirst、pop；再 push 两个元素并观察顺序。
- 验收证据：写出元素为 null 为什么会与 poll/peek 的空信号冲突；沿 addFirst 跟到 grow，区分业务容量与底层数组容量。

固定源码 tag jdk-17+35 对应 commit dfacda488bfbe2e11e8d607a6d08527710286982。若运行 JVM 为21，IDE默认打开的21源码不等于本题17基线；对比可以做，但必须分别标记版本，不能将21调试结果当作17验证。

## 面试表达与复盘

回答以下问题，每项用代码或测试支撑：

1. 你的实现维护什么不变量？失败后会留下什么状态？
2. 时间/空间复杂度是什么？最坏与均摊/预期是否相同？
3. 哪个测试会击穿一个看似合理的错误实现？
4. 与 JDK 实现有哪些差异？如果并发访问会发生什么？

完成后记录：首次测试结果、用了第几阶提示、实际耗时、失败原因、24 小时后能否无提示重写。不要用“测试全绿”替代源码解释与口述验收。
