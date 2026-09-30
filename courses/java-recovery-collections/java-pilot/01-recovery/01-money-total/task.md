# 01 · 金额累计：重新找回编码手感

预计 35 分钟。先独立写 15–20 分钟，再按需展开提示；完成后运行检查、口述设计、补一条自己的边界测试。

## 业务背景与目标

用 long 表示分，只累计 PAID。空列表为 0；列表、元素、status 为 null 时抛 NullPointerException；任何订单金额为负（包括未付款订单）抛 IllegalArgumentException；long 累加溢出抛 ArithmeticException。不得改动输入。

## 示例

[PAID:120, PENDING:900, PAID:80] → 200

## 实作要求

只修改实现文件的答案占位区域，保留公开 API。可在可见的 PaidTotalsExamplesTest.java 中补充自己的 @Test；参考样例不会代替隐藏契约测试。先把输入、输出、异常和是否修改状态写成小清单。先写直观正确实现，再讨论优化。编译通过不等于通过契约。

## 三阶提示

<div class="hint" title="提示 1">
先写 for-each 和状态判断，不要立即写 Stream
</div>

<div class="hint" title="提示 2">
把输入校验与业务筛选分开：未付款订单也要校验
</div>

<div class="hint" title="提示 3">
Math.addExact 能把静默溢出变成可观察错误
</div>

## 源码伴读（固定版本）

打开 [OpenJDK 17 GA，jdk-17+35](https://github.com/openjdk/jdk/blob/jdk-17%2B35/src/java.base/share/classes/java/lang/Math.java)，使用 IDE 搜索相关方法。先预测行为，再从分支、字段和调用关系找证据。不能只背结论；记录“类/方法 → 条件 → 状态变化 → 与本题的差异”。

## 源码定位、实验与证据

- 精确定位：Math.addExact(long,long)
- 可复现实验：分别输入 (Long.MAX_VALUE,0)、(Long.MAX_VALUE,1)、(-1,1)。在源码中标记溢出判断表达式与抛异常位置。
- 验收证据：提交一张“操作数符号→结果符号→是否溢出”表，并解释普通 + 为何不会自动报错。不要把本题非负金额校验和 addExact 的通用整数能力混为一谈。

固定源码 tag jdk-17+35 对应 commit dfacda488bfbe2e11e8d607a6d08527710286982。若运行 JVM 为21，IDE默认打开的21源码不等于本题17基线；对比可以做，但必须分别标记版本，不能将21调试结果当作17验证。

## 面试表达与复盘

回答以下问题，每项用代码或测试支撑：

1. 你的实现维护什么不变量？失败后会留下什么状态？
2. 时间/空间复杂度是什么？最坏与均摊/预期是否相同？
3. 哪个测试会击穿一个看似合理的错误实现？
4. 与 JDK 实现有哪些差异？如果并发访问会发生什么？

完成后记录：首次测试结果、用了第几阶提示、实际耗时、失败原因、24 小时后能否无提示重写。不要用“测试全绿”替代源码解释与口述验收。
