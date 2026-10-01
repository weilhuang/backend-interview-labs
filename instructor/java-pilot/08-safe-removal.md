# 08 · Iterator 与安全原地删除 · 教师解析

参考实现位于作者模式任务的 src，占位区由 Academy 预览/导出时替换。请先练习再看。

fail-fast 只是尽力检测错误，不是并发安全保证。LinkedList 迭代删除 O(n)；ArrayList 每次删除需要搬移，最坏 O(n²)。因此 Iterator 正确不等于最快；ArrayList 的 removeIf 批量压缩是后续优化方向。

## 源码定位

https://github.com/openjdk/jdk/blob/jdk-21%2B35/src/java.base/share/classes/java/util/ArrayList.java

## 关键反例

[-1,-2,0,3,-4] → [0,3]，返回 3

## 评分

- 契约与边界 40%
- 实现与测试 30%
- 复杂度和源码证据 20%
- 两分钟表达 10%

参考实现不代表唯一正确实现；复杂度、线程安全与失败原子性需人工复核。
