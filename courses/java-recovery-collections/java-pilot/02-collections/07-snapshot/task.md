# 07 · subList 视图、快照与不可变

预计 45 分钟。先独立写 15–20 分钟，再按需展开提示；完成后运行检查、口述设计、补一条自己的边界测试。

## 业务背景与目标

返回 input[from,to) 的结构不可变、与原列表结构独立的浅快照；允许空区间。不允许选中区间含 null，但区间之外的 null 不影响。非法下标（包括 from>to）抛 IndexOutOfBoundsException。null 输入抛 NullPointerException。元素对象不要求深拷贝。

## 示例

原列表 set/clear 后快照仍为旧序列；快照里的可变元素仍可改变

## 实作要求

只修改实现文件的答案占位区域，保留公开 API。可在可见的 SnapshotsExamplesTest.java 中补充自己的 @Test；参考样例不会代替隐藏契约测试。先把输入、输出、异常和是否修改状态写成小清单。先写直观正确实现，再讨论优化。编译通过不等于通过契约。

## 三阶提示

<div class="hint" title="提示 1">
subList 返回的是视图，不是快照
</div>

<div class="hint" title="提示 2">
unmodifiableList 包裹视图只限制通过包装器修改
</div>

<div class="hint" title="提示 3">
List.copyOf 拷贝结构并拒绝 null；浅拷贝仍共享元素引用
</div>

## 源码伴读（固定版本）

打开 [OpenJDK 17 GA，jdk-17+35](https://github.com/openjdk/jdk/blob/jdk-17%2B35/src/java.base/share/classes/java/util/ArrayList.java)，使用 IDE 搜索相关方法。先预测行为，再从分支、字段和调用关系找证据。不能只背结论；记录“类/方法 → 条件 → 状态变化 → 与本题的差异”。

## 源码定位、实验与证据

- 精确定位：ArrayList.subList、SubList.root/parent/offset、SubList.checkForComodification
- 可复现实验：建立父列表和 subList；先 parent.set，再在独立的新样例里 parent.add；对比 List.copyOf(subList) 结果。
- 验收证据：分别记录“结构修改”与“元素替换”的区别；证明只读包装仍可能联动原列表，结构快照不等于元素深拷贝。

固定源码 tag jdk-17+35 对应 commit dfacda488bfbe2e11e8d607a6d08527710286982。若运行 JVM 为21，IDE默认打开的21源码不等于本题17基线；对比可以做，但必须分别标记版本，不能将21调试结果当作17验证。

## 面试表达与复盘

回答以下问题，每项用代码或测试支撑：

1. 你的实现维护什么不变量？失败后会留下什么状态？
2. 时间/空间复杂度是什么？最坏与均摊/预期是否相同？
3. 哪个测试会击穿一个看似合理的错误实现？
4. 与 JDK 实现有哪些差异？如果并发访问会发生什么？

完成后记录：首次测试结果、用了第几阶提示、实际耗时、失败原因、24 小时后能否无提示重写。不要用“测试全绿”替代源码解释与口述验收。
