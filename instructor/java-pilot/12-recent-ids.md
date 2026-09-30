# 12 · 近期去重窗口：组合数据结构 · 教师解析

参考实现位于作者模式任务的 src，占位区由 Academy 预览/导出时替换。请先练习再看。

不变量：order.size==seen.size≤capacity，order 无重复，集合与队列元素相同。预期 offer O(1)，快照 O(k)。这是有限窗口的尽力去重；重启、跨进程、窗口淘汰后都不提供永久幂等。连接后续 Redis/MQ 课程的持久幂等键和事务边界。

## 源码定位

https://github.com/openjdk/jdk/blob/jdk-21%2B35/src/java.base/share/classes/java/util/ArrayDeque.java

## 关键反例

容量2：a,b,a,c,a 的接受结果 true,true,false,true,true

## 评分

- 契约与边界 40%
- 实现与测试 30%
- 复杂度和源码证据 20%
- 两分钟表达 10%

参考实现不代表唯一正确实现；复杂度、线程安全与失败原子性需人工复核。
