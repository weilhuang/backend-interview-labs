# 10 · HashMap 扰动与桶索引

预计 60 分钟。先独立写 15–20 分钟，再按需展开提示；完成后运行检查、口述设计、补一条自己的边界测试。

## 业务背景与目标

实现 OpenJDK17 HashMap 的 int hash 扰动公式和正 2 的幂容量下的桶索引；参数 hash 是原始 hashCode，不处理对象或 null。非法容量抛 IllegalArgumentException。不要用 abs(hash)%capacity。

## 示例

hash=0x00010000,capacity=16 → index=1

## 实作要求

只修改实现文件的答案占位区域，保留公开 API。可在可见的 HashIndexExamplesTest.java 中补充自己的 @Test；参考样例不会代替隐藏契约测试。先把输入、输出、异常和是否修改状态写成小清单。先写直观正确实现，再讨论优化。编译通过不等于通过契约。

## 三阶提示

<div class="hint" title="提示 1">
>>> 是无符号右移，>> 会符号扩展
</div>

<div class="hint" title="提示 2">
2 的幂容量可以用按位与保留低位
</div>

<div class="hint" title="提示 3">
容量翻倍后，一个旧桶的节点只可能留原位或移动 oldCapacity
</div>

## 源码伴读（固定版本）

打开 [OpenJDK 17 GA，jdk-17+35](https://github.com/openjdk/jdk/blob/jdk-17%2B35/src/java.base/share/classes/java/util/HashMap.java)，使用 IDE 搜索相关方法。先预测行为，再从分支、字段和调用关系找证据。不能只背结论；记录“类/方法 → 条件 → 状态变化 → 与本题的差异”。

## 源码定位、实验与证据

- 精确定位：HashMap.hash（约335行）、putVal（约622行）、resize（约674行）、treeifyBin（约752行）
- 可复现实验：在匹配的 JDK17 调试源码上，令自定义 Key 的 hashCode 恒为 1、equals 按唯一 id，比较 new HashMap<>(64) 与 new HashMap<>(16) 逐个 put 1..12 的过程。在 treeifyBin 和 resize 设断点；另记录旧容量16时 hash=1、17、33 的桶迁移。
- 验收证据：提交逐次插入表：size、table.length、链/树、binCount、是否先扩容。核对 TREEIFY_THRESHOLD=8、MIN_TREEIFY_CAPACITY=64 与实际 put 路径的计数方式；绝不能只写“到8就一定树化”。再从 resize 的 oldCap 位判断推导桶拆分；UNTREEIFY_THRESHOLD=6 的使用场景需单独定位，不能与普通 remove 简单画等号。

固定源码 tag jdk-17+35 对应 commit dfacda488bfbe2e11e8d607a6d08527710286982。若运行 JVM 为21，IDE默认打开的21源码不等于本题17基线；对比可以做，但必须分别标记版本，不能将21调试结果当作17验证。

## 面试表达与复盘

回答以下问题，每项用代码或测试支撑：

1. 你的实现维护什么不变量？失败后会留下什么状态？
2. 时间/空间复杂度是什么？最坏与均摊/预期是否相同？
3. 哪个测试会击穿一个看似合理的错误实现？
4. 与 JDK 实现有哪些差异？如果并发访问会发生什么？

完成后记录：首次测试结果、用了第几阶提示、实际耗时、失败原因、24 小时后能否无提示重写。不要用“测试全绿”替代源码解释与口述验收。
