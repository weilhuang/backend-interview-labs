# 02 · 解析边界与稳定去重

预计 40 分钟。先独立写 15–20 分钟，再按需展开提示；完成后运行检查、口述设计、补一条自己的边界测试。

## 业务背景与目标

输入是逗号分隔的正 int ID；允许 token 两端 ASCII 空白、前导零，去重后保留首次出现顺序。空白整串返回新的可变空列表；不允许符号、小数、非 ASCII 数字、空 token、0、溢出。非法格式抛 IllegalArgumentException（NumberFormatException 是其子类）；null 抛 NullPointerException。

## 示例

"3,1,03,2" → [3,1,2]；"1," 必须失败

## 实作要求

只修改实现文件的答案占位区域，保留公开 API。可在可见的 IdParserExamplesTest.java 中补充自己的 @Test；参考样例不会代替隐藏契约测试。先把输入、输出、异常和是否修改状态写成小清单。先写直观正确实现，再讨论优化。编译通过不等于通过契约。

## 三阶提示

<div class="hint" title="提示 1">
String.split 默认会丢掉结尾空串，想想 limit 参数
</div>

<div class="hint" title="提示 2">
查重与输出顺序需要同时满足；比较 HashSet 和 LinkedHashSet
</div>

<div class="hint" title="提示 3">
解析后去重，而不是原始字符串去重：03 和 3 是同一个 ID
</div>

## 源码伴读（固定版本）

打开 [OpenJDK 17 GA，jdk-17+35](https://github.com/openjdk/jdk/blob/jdk-17%2B35/src/java.base/share/classes/java/lang/String.java)，使用 IDE 搜索相关方法。先预测行为，再从分支、字段和调用关系找证据。不能只背结论；记录“类/方法 → 条件 → 状态变化 → 与本题的差异”。

## 源码定位、实验与证据

- 精确定位：String.split(String,int) 与 split(String)
- 可复现实验：用 JShell 比较 "1,".split(",") 和 "1,".split(",",-1) 的长度；再看 ",1" 和 ""。
- 验收证据：记录 limit 三类（正、零、负）的差异。说明本题为什么先判断整体空白，以及前导零何时变成数值身份。

固定源码 tag jdk-17+35 对应 commit dfacda488bfbe2e11e8d607a6d08527710286982。若运行 JVM 为21，IDE默认打开的21源码不等于本题17基线；对比可以做，但必须分别标记版本，不能将21调试结果当作17验证。

## 面试表达与复盘

回答以下问题，每项用代码或测试支撑：

1. 你的实现维护什么不变量？失败后会留下什么状态？
2. 时间/空间复杂度是什么？最坏与均摊/预期是否相同？
3. 哪个测试会击穿一个看似合理的错误实现？
4. 与 JDK 实现有哪些差异？如果并发访问会发生什么？

完成后记录：首次测试结果、用了第几阶提示、实际耗时、失败原因、24 小时后能否无提示重写。不要用“测试全绿”替代源码解释与口述验收。
