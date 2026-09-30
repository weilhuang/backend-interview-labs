# 11 · 基于访问顺序的 LRU 缓存

预计 60 分钟。先独立写 15–20 分钟，再按需展开提示；完成后运行检查、口述设计、补一条自己的边界测试。

## 业务背景与目标

有界单线程 LRU：成功 get 刷新访问顺序；put 新键或更新旧键都刷新。超容量淘汰最久未访问键。未命中不影响顺序；拒绝 null key/value，失败不能改变状态。keysLeastToMostRecent 返回不可修改、结构独立的键快照。capacity 必须 >0。

## 示例

put(a),put(b),get(a),put(c)，容量2 → 淘汰 b

## 实作要求

只修改实现文件的答案占位区域，保留公开 API。可在可见的 LruCacheExamplesTest.java 中补充自己的 @Test；参考样例不会代替隐藏契约测试。先把输入、输出、异常和是否修改状态写成小清单。先写直观正确实现，再讨论优化。编译通过不等于通过契约。

## 三阶提示

<div class="hint" title="提示 1">
LinkedHashMap 有 insertion-order 和 access-order 两种模式
</div>

<div class="hint" title="提示 2">
覆盖已有 key 不应误删额外元素
</div>

<div class="hint" title="提示 3">
先校验完整输入，再 put，再判断是否超限
</div>

## 源码伴读（固定版本）

打开 [OpenJDK 17 GA，jdk-17+35](https://github.com/openjdk/jdk/blob/jdk-17%2B35/src/java.base/share/classes/java/util/LinkedHashMap.java)，使用 IDE 搜索相关方法。先预测行为，再从分支、字段和调用关系找证据。不能只背结论；记录“类/方法 → 条件 → 状态变化 → 与本题的差异”。

## 源码定位、实验与证据

- 精确定位：LinkedHashMap.get、afterNodeAccess、afterNodeInsertion、removeEldestEntry
- 可复现实验：在 accessOrder=true 的映射执行 put(a),put(b),get(a),get(missing),put(a,new)。观察 head、tail 和 modCount；再对照 accessOrder=false。
- 验收证据：用证据解释 get 为什么可能修改结构，以及 iterator 与访问刷新并用的风险。找出自动 removeEldestEntry 钩子和本题显式淘汰写法的差异。

固定源码 tag jdk-17+35 对应 commit dfacda488bfbe2e11e8d607a6d08527710286982。若运行 JVM 为21，IDE默认打开的21源码不等于本题17基线；对比可以做，但必须分别标记版本，不能将21调试结果当作17验证。

## 面试表达与复盘

回答以下问题，每项用代码或测试支撑：

1. 你的实现维护什么不变量？失败后会留下什么状态？
2. 时间/空间复杂度是什么？最坏与均摊/预期是否相同？
3. 哪个测试会击穿一个看似合理的错误实现？
4. 与 JDK 实现有哪些差异？如果并发访问会发生什么？

完成后记录：首次测试结果、用了第几阶提示、实际耗时、失败原因、24 小时后能否无提示重写。不要用“测试全绿”替代源码解释与口述验收。
