# 11 · 基于访问顺序的 LRU 缓存 · 教师解析

参考实现位于作者模式任务的 src，占位区由 Academy 预览/导出时替换。请先练习再看。

预期 get/put O(1)，快照 O(n)。访问顺序模式中 get 会修改链表顺序，因此“只读请求”也不能直接并发调用。生产缓存还涉及过期、加载、淘汰统计和内存成本；不能把此练习称为线程安全缓存。

## 源码定位

https://github.com/openjdk/jdk/blob/jdk-17%2B35/src/java.base/share/classes/java/util/LinkedHashMap.java

## 关键反例

put(a),put(b),get(a),put(c)，容量2 → 淘汰 b

## 评分

- 契约与边界 40%
- 实现与测试 30%
- 复杂度和源码证据 20%
- 两分钟表达 10%

参考实现不代表唯一正确实现；复杂度、线程安全与失败原子性需人工复核。
