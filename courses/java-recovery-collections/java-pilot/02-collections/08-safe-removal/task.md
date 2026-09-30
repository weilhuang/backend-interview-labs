# 08 · Iterator 与安全原地删除

预计 45 分钟。先独立写 15–20 分钟，再按需展开提示；完成后运行检查、口述设计、补一条自己的边界测试。

## 业务背景与目标

对支持 Iterator.remove 的可变 List<Integer> 原地删除所有负数，保留其他元素顺序，返回删除数量。先完整校验 null 元素，非法输入失败后必须保持列表不变。不要求支持不可修改/定长列表。需用 Iterator，不能用索引删除或 removeIf 代替本题练习。

## 示例

[-1,-2,0,3,-4] → [0,3]，返回 3

## 实作要求

只修改实现文件的答案占位区域，保留公开 API。可在可见的 SafeRemovalExamplesTest.java 中补充自己的 @Test；参考样例不会代替隐藏契约测试。先把输入、输出、异常和是否修改状态写成小清单。先写直观正确实现，再讨论优化。编译通过不等于通过契约。

## 三阶提示

<div class="hint" title="提示 1">
先做一遍校验再修改，保证本题要求的失败原子性
</div>

<div class="hint" title="提示 2">
增强 for 本身背后也是迭代器，但不能随意 values.remove
</div>

<div class="hint" title="提示 3">
让同一个 Iterator 执行 next 和 remove
</div>

## 源码伴读（固定版本）

打开 [OpenJDK 17 GA，jdk-17+35](https://github.com/openjdk/jdk/blob/jdk-17%2B35/src/java.base/share/classes/java/util/ArrayList.java)，使用 IDE 搜索相关方法。先预测行为，再从分支、字段和调用关系找证据。不能只背结论；记录“类/方法 → 条件 → 状态变化 → 与本题的差异”。

## 源码定位、实验与证据

- 精确定位：ArrayList.Itr.next/remove/checkForComodification、fastRemove、removeIf
- 可复现实验：对 [-1,-2,0] 逐次记录 cursor、lastRet、expectedModCount、modCount；比较 Iterator.remove 与列表直接 remove。
- 验收证据：指出 Iterator.remove 如何恢复游标和版本计数。再跟 fastRemove 的数组搬移；说明为何本题正确解对 ArrayList 最坏仍是二次复杂度。

固定源码 tag jdk-17+35 对应 commit dfacda488bfbe2e11e8d607a6d08527710286982。若运行 JVM 为21，IDE默认打开的21源码不等于本题17基线；对比可以做，但必须分别标记版本，不能将21调试结果当作17验证。

## 面试表达与复盘

回答以下问题，每项用代码或测试支撑：

1. 你的实现维护什么不变量？失败后会留下什么状态？
2. 时间/空间复杂度是什么？最坏与均摊/预期是否相同？
3. 哪个测试会击穿一个看似合理的错误实现？
4. 与 JDK 实现有哪些差异？如果并发访问会发生什么？

完成后记录：首次测试结果、用了第几阶提示、实际耗时、失败原因、24 小时后能否无提示重写。不要用“测试全绿”替代源码解释与口述验收。
