# 06 · 聚合、Comparator 与确定性 Top-K · 教师解析

参考实现位于作者模式任务的 src，占位区由 Academy 预览/导出时替换。请先练习再看。

n 个 token、m 个不同词：预期 O(n+m log m) 时间，O(m) 空间。大 m 小 k 时可用堆降到 O(m log k)，但需要同样稳定的平票规则。本题先做清楚完整排序；不要为了堆牺牲契约。

## 源码定位

https://github.com/openjdk/jdk/blob/jdk-21%2B35/src/java.base/share/classes/java/util/Comparator.java

## 关键反例

[b,a,b,c,a]，k=2 → [(a,2),(b,2)]

## 评分

- 契约与边界 40%
- 实现与测试 30%
- 复杂度和源码证据 20%
- 两分钟表达 10%

参考实现不代表唯一正确实现；复杂度、线程安全与失败原子性需人工复核。
