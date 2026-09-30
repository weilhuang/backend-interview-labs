# 05 · 不可变 Map Key 的身份契约

预计 45 分钟。先独立写 15–20 分钟，再按需展开提示；完成后运行检查、口述设计、补一条自己的边界测试。

## 业务背景与目标

tenant 与 userId 共同定义身份，tenant 区分大小写，保留原样，不隐式 trim；构造器已经校验。实现 equals 与 hashCode，不要求不同 key 的 hashCode 都不同。不能改变类的不可变结构。

## 示例

两个 new TenantKey("acme",7) 能查到同一个 HashMap 条目

## 实作要求

只修改实现文件的答案占位区域，保留公开 API。可在可见的 TenantKeyExamplesTest.java 中补充自己的 @Test；参考样例不会代替隐藏契约测试。先把输入、输出、异常和是否修改状态写成小清单。先写直观正确实现，再讨论优化。编译通过不等于通过契约。

## 三阶提示

<div class="hint" title="提示 1">
先排除 null 和不兼容类型
</div>

<div class="hint" title="提示 2">
两个身份字段都必须参与 equals
</div>

<div class="hint" title="提示 3">
同一个 tenant 内容可能来自不同 String 实例，不能用 ==
</div>

## 源码伴读（固定版本）

打开 [OpenJDK 17 GA，jdk-17+35](https://github.com/openjdk/jdk/blob/jdk-17%2B35/src/java.base/share/classes/java/util/HashMap.java)，使用 IDE 搜索相关方法。先预测行为，再从分支、字段和调用关系找证据。不能只背结论；记录“类/方法 → 条件 → 状态变化 → 与本题的差异”。

## 源码定位、实验与证据

- 精确定位：HashMap.hash、getNode、putVal
- 可复现实验：用两个不同实例但身份相同的 TenantKey 进行 put/get；再用 tenant 分别为 Aa 与 BB 的 key。
- 验收证据：标出先比较 hash、再比较 ==/equals 的分支。写出只实现 equals 而不匹配 hashCode 为什么会出错；不得声称不同 key 必须有不同 hash。

固定源码 tag jdk-17+35 对应 commit dfacda488bfbe2e11e8d607a6d08527710286982。若运行 JVM 为21，IDE默认打开的21源码不等于本题17基线；对比可以做，但必须分别标记版本，不能将21调试结果当作17验证。

## 面试表达与复盘

回答以下问题，每项用代码或测试支撑：

1. 你的实现维护什么不变量？失败后会留下什么状态？
2. 时间/空间复杂度是什么？最坏与均摊/预期是否相同？
3. 哪个测试会击穿一个看似合理的错误实现？
4. 与 JDK 实现有哪些差异？如果并发访问会发生什么？

完成后记录：首次测试结果、用了第几阶提示、实际耗时、失败原因、24 小时后能否无提示重写。不要用“测试全绿”替代源码解释与口述验收。
