# 03 · 泛型、异常与有界栈 · 教师解析

参考实现位于作者模式任务的 src，占位区由 Academy 预览/导出时替换。请先练习再看。

为何选择 ArrayDeque 而不是 Stack？解释 Optional 的空状态与不接受 null 的关系。通常操作均摊 O(1)，扩容单次可能 O(n)。容量是业务上限，不代表 ArrayDeque 已预分配恰好这些槽位。

## 源码定位

https://github.com/openjdk/jdk/blob/jdk-21%2B35/src/java.base/share/classes/java/util/ArrayDeque.java

## 关键反例

push(a),push(b),peek(),pop(),pop() → b,b,a

## 评分

- 契约与边界 40%
- 实现与测试 30%
- 复杂度和源码证据 20%
- 两分钟表达 10%

参考实现不代表唯一正确实现；复杂度、线程安全与失败原子性需人工复核。
