# 04 · equals、hashCode 与稳定去重 · 教师解析

参考实现位于作者模式任务的 src，占位区由 Academy 预览/导出时替换。请先练习再看。

预期 O(n) 时间、O(k) 额外空间，依赖合理散列；不能绝对保证所有输入 O(n)。不要按 hashCode 去重；HashSet 无顺序保证，TreeSet 则按比较器定义相等。

## 源码定位

https://github.com/openjdk/jdk/blob/jdk-17%2B35/src/java.base/share/classes/java/util/LinkedHashSet.java

## 关键反例

[z,a,null,a,z] → [z,a,null]

## 评分

- 契约与边界 40%
- 实现与测试 30%
- 复杂度和源码证据 20%
- 两分钟表达 10%

参考实现不代表唯一正确实现；复杂度、线程安全与失败原子性需人工复核。
