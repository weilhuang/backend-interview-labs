# 01 · 金额累计：重新找回编码手感

## 依赖与完整项目结构

本题使用完整 JDK21、Gradle8.10.2、JUnit Jupiter5.11.4 / Platform1.11.4，编译使用 --release21。源码仓库自带 Gradle Wrapper；Academy 导入课程由 IDE 管理 Gradle。无需为每题新建工程，具体入口见下面的运行说明。

```text
01-money-total/
+-- task.md                       # 题目、提示、源码讲解、标准答案
+-- task-info.yaml                # Academy 文件与占位区配置
+-- src/labs/PaidTotals.java             # 你需要实现的公开接口
+-- src/labs/PaidTotalsUsage.java        # 完整 main 调用端
+-- test/PaidTotalsTest.java             # 完整契约测试，全部可见
+-- test/PaidTotalsExamplesTest.java     # 可扩展的使用样例测试
```

预计 35 分钟。先独立写 15–20 分钟，再按需展开提示；完成后运行检查、口述设计、补一条自己的边界测试。

## 业务背景与目标

用 long 表示分，只累计 PAID。空列表为 0；列表、元素、status 为 null 时抛 NullPointerException；任何订单金额为负（包括未付款订单）抛 IllegalArgumentException；long 累加溢出抛 ArithmeticException。不得改动输入。

## 示例

[PAID:120, PENDING:900, PAID:80] → 200

## 实作要求

只修改实现文件的答案占位区域，保留公开 API。可在可见的 PaidTotalsExamplesTest.java 中补充自己的 @Test；所有测试代码均可见；参考样例不会代替完整契约测试。先把输入、输出、异常和是否修改状态写成小清单。先写直观正确实现，再讨论优化。编译通过不等于通过契约。

## 三阶提示

### 提示1

先写 for-each 和状态判断，不要立即写 Stream

### 提示2

把输入校验与业务筛选分开：未付款订单也要校验

### 提示3

Math.addExact 能把静默溢出变成可观察错误

## 源码伴读（固定版本）

打开 [OpenJDK 21 GA，jdk-21+35](https://github.com/openjdk/jdk/blob/jdk-21%2B35/src/java.base/share/classes/java/lang/Math.java)，使用 IDE 搜索相关方法。先预测行为，再从分支、字段和调用关系找证据。不能只背结论；记录“类/方法 → 条件 → 状态变化 → 与本题的差异”。

## 源码定位、实验与证据

- 精确定位：Math.addExact(long,long)
- 可复现实验：分别输入 (Long.MAX_VALUE,0)、(Long.MAX_VALUE,1)、(-1,1)。在源码中标记溢出判断表达式与抛异常位置。
- 验收证据：提交一张“操作数符号→结果符号→是否溢出”表，并解释普通 + 为何不会自动报错。不要把本题非负金额校验和 addExact 的通用整数能力混为一谈。

固定源码 tag jdk-21+35 对应 commit 890adb6410dab4606a4f26a942aed02fb2f55387。本题固定源码为21 GA；若运行的是21的后续更新，调试器源码与字节码应匹配该更新版本。可以对照差异，但请分别记录源码tag和实际运行时补丁版本。

## 面试表达与复盘

回答以下问题，每项用代码或测试支撑：

1. 你的实现维护什么不变量？失败后会留下什么状态？
2. 时间/空间复杂度是什么？最坏与均摊/预期是否相同？
3. 哪个测试会击穿一个看似合理的错误实现？
4. 与 JDK 实现有哪些差异？如果并发访问会发生什么？

完成后记录：首次测试结果、用了第几阶提示、实际耗时、失败原因、24 小时后能否无提示重写。不要用“测试全绿”替代源码解释与口述验收。


## 完整调用示例

以下文件已经放在工程中，可直接打开或通过本题 run 任务执行：

```java
package labs;

import java.util.*;

// 完整调用端：先构造输入，再调用业务接口，最后打印可核对的结果。
public final class PaidTotalsUsage {
    private PaidTotalsUsage() {}

    public static void main(String[] args) {
        var orders = List.of(
            new PaidTotals.Order(120, PaidTotals.Status.PAID),
            new PaidTotals.Order(900, PaidTotals.Status.PENDING),
            new PaidTotals.Order(80, PaidTotals.Status.PAID));
        System.out.println("已付款总额（分）=" + PaidTotals.total(orders));
    }
}
```

期望输出：

```text
已付款总额（分）=200
```

## 写代码、使用接口、验证结果

**Academy 导入或预览模式**：用题面底部的 **Check** 验证答案；打开 `src/labs/PaidTotalsUsage.java`，点击 `main` 旁的运行图标执行调用示例。也可在 Gradle 工具窗口选择本题模块的 `test` 或 `run` 任务。未完成 TODO 时，测试或调用失败是预期行为。

**源码仓库或普通 Gradle 学员副本模式**：仅在包含 `gradlew`、`gradlew.bat` 和 `gradle/wrapper/gradle-wrapper.jar` 的工程根目录执行下面命令。普通学员副本由 `authoring/materialize_learner.py` 生成。

实际验证的 Academy 官方导出 ZIP 和干净导入目录不包含上述三个 Wrapper 文件，不能直接在该导入目录执行 `./gradlew`。以下命令保留给源码与普通 Gradle 工程入口：

```sh
./gradlew :java-pilot-01-recovery-01-money-total:test
./gradlew :java-pilot-01-recovery-01-money-total:run
```

1. 先读完整调用端和两份测试，列出正常路径、边界及异常
2. 自己填写答案区；Academy 模式先点 Check 再运行 Usage，源码模式先跑 test 再跑 run，对照上面的输出
3. 在 ExamplesTest 增加一个尚未覆盖的边界；解释为何预期如此
4. 有错误先判断是编译、契约、状态变更还是输出理解错误，再修改实现
5. 测试和调用端都正确后，按下面的源码机制口述，再与标准答案对照

## 核心原理与源码解释

```text
订单输入 --> 完整校验 --> 状态筛选 --> 精确加法 --> 总额
             |             |            |
           非法失败      未付款跳过    溢出失败
```

这里有两个不同层次的不变量：每个订单都满足输入契约；sum 始终只等于已经访问的 PAID 金额之和。先校验、后筛选，因此 CANCELLED 的负金额也不能混过关。Math.addExact 并不是“大整数”，它在 long 的固定范围内计算并在溢出时抛异常。固定精度业务金额通常可用最小货币单位整数存储，但多币种、汇率、税率和小数位舍入仍需要独立规则。

循环解的时间是 O(n)、额外空间 O(1)。Long.MAX_VALUE+1 的错误不是精度稍有偏差，而是有符号整数回绕；这就是为什么测试必须覆盖边界。参考解没有修改输入，也没有共享累加器，所以不会留下半更新的外部集合。

## 标准答案与逐步解析

以下是本题公开的完整标准答案。建议独立尝试后再对照；答案随课程提供，不依赖隐藏文件、外部教师目录或折叠渲染功能。不同写法只要满足契约与复杂度要求也可以。

```java
// 标准实现位于作者占位区；学员填写同一公开接口，题面末尾提供完整答案与解析。
package labs;
import java.util.List;
import java.util.Objects;
public final class PaidTotals {
    public enum Status { PAID, CANCELLED, PENDING }
    public record Order(long cents, Status status) {}
    private PaidTotals() {}
    public static long total(List<Order> orders) {
        Objects.requireNonNull(orders, "orders");
        long sum = 0;
        for (Order order : orders) {
            Objects.requireNonNull(order, "order");
            Objects.requireNonNull(order.status(), "status");
            if (order.cents() < 0) throw new IllegalArgumentException("negative cents");
            if (order.status() == Status.PAID) sum = Math.addExact(sum, order.cents());
        }
        return sum;
    }
}
```

对照顺序：先看输入校验与异常，再看核心状态更新，再看返回值和是否泄漏可变视图；最后用完整契约测试逐项证明行为。本题另一种正确写法及错误变体用于作者质量回归，不是对学员实现风格的强制要求。

## 面试题递进与参考表达

### 1. 机制：为什么 addExact 比普通 + 更适合这里？

参考表达：它把超出 long 范围的结果转为 ArithmeticException，防止静默负数进入后续业务。

### 2. 边界：过滤后再校验能否通过？

参考表达：不能；本题要求未付款订单也满足输入契约。

### 3. 取舍：Stream 比循环更好吗？

参考表达：两者可表达同一逻辑；循环更容易清楚标明逐项校验和失败点，选择应服务可读性。

### 4. 追问：累计结果超出 long 范围时怎么设计？

参考表达：先确认业务最大值与失败策略；需要任意精度时可用 BigInteger，金额运算和舍入可按领域规则选 BigDecimal。
