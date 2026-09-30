# 06 · 聚合、Comparator 与确定性 Top-K

预计 50 分钟。先独立写 15–20 分钟，再按需展开提示；完成后运行检查、口述设计、补一条自己的边界测试。

## 业务背景与目标

输入已经分词：每个 token 使用 trim 后按 Locale.ROOT 小写，忽略空串；按次数降序，次数相同按 String 自然序升序，返回前 k 个新的可变 Count 列表。k<0 抛 IllegalArgumentException。输入/元素 null 抛 NullPointerException，k=0 也必须校验所有元素。不得修改输入。

## 示例

[b,a,b,c,a]，k=2 → [(a,2),(b,2)]

## 实作要求

只修改实现文件的答案占位区域，保留公开 API。可在可见的 TopWordsExamplesTest.java 中补充自己的 @Test；参考样例不会代替隐藏契约测试。先把输入、输出、异常和是否修改状态写成小清单。先写直观正确实现，再讨论优化。编译通过不等于通过契约。

## 三阶提示

<div class="hint" title="提示 1">
先计数，再排序，再截取，分别写测试
</div>

<div class="hint" title="提示 2">
不指定 Locale 的大小写转换可能受机器默认语言影响
</div>

<div class="hint" title="提示 3">
比较器不要做计数相减并强转 int；给平票明确顺序
</div>

## 源码伴读（固定版本）

打开 [OpenJDK 17 GA，jdk-17+35](https://github.com/openjdk/jdk/blob/jdk-17%2B35/src/java.base/share/classes/java/util/Comparator.java)，使用 IDE 搜索相关方法。先预测行为，再从分支、字段和调用关系找证据。不能只背结论；记录“类/方法 → 条件 → 状态变化 → 与本题的差异”。

## 源码定位、实验与证据

- 精确定位：Comparator.comparingLong、reversed、thenComparing
- 可复现实验：用 b:2、a:2、c:3 比较两种排序键顺序；在测试中临时将默认 Locale 设为 tr-TR（最后恢复）。
- 验收证据：解释 reversed 放在整个链末尾与只反转计数排序的区别。补充一个平票反例；不要依赖 HashMap 当前碰巧的遍历顺序。

固定源码 tag jdk-17+35 对应 commit dfacda488bfbe2e11e8d607a6d08527710286982。若运行 JVM 为21，IDE默认打开的21源码不等于本题17基线；对比可以做，但必须分别标记版本，不能将21调试结果当作17验证。

## 面试表达与复盘

回答以下问题，每项用代码或测试支撑：

1. 你的实现维护什么不变量？失败后会留下什么状态？
2. 时间/空间复杂度是什么？最坏与均摊/预期是否相同？
3. 哪个测试会击穿一个看似合理的错误实现？
4. 与 JDK 实现有哪些差异？如果并发访问会发生什么？

完成后记录：首次测试结果、用了第几阶提示、实际耗时、失败原因、24 小时后能否无提示重写。不要用“测试全绿”替代源码解释与口述验收。
