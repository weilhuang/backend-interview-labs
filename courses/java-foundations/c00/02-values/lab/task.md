# C00-02 · 金额舍入、值相等与对象身份

## 企业场景与进入条件

结算服务收到1、1.0和1.00，必须统一值语义，同时明确半分舍入规则。先修C00-01；120分钟。示例1.005变1.00，1.015变1.02。

## 合同、输入输出与修改范围

Money.of接收十进制文本，拒绝null、坏数值和任何负原始金额（-0.001也拒绝）；HALF_EVEN量化为2位小数，最终分值必须能放long。plus/times返回新Money，乘数非负。equals/hashCode在统一scale后保持一致；OrderId修剪首尾空白，长度1至64。

本题在独立完整工程中运行：src是实现与调用方，test是全部公开测试，common是本课程内的完整领域checkpoint。只改答案区，接口和测试合同不变；可在test补自己的回归。标准解始终直接可读，未隐藏测试或答案。

## 概念与ASCII图

```text
十进制文本 -> BigDecimal原值 -> 非负校验 -> HALF_EVEN两位
                                             |
                                             v
                           规范化Money -> equals/hashCode一致
身份== 与 值equals：两条不同问题
```

## 分步使用与验证

运行路线先区分：以下./gradlew命令适用于带Wrapper的源码仓库课程目录。若从Academy官方ZIP导入，用本题Check、Usage main运行按钮或IDE Gradle工具窗口的对应任务；Academy2026.9官方ZIP实际会剔除Wrapper脚本和JAR，不能承诺导入目录的终端./gradlew可用。完整CLI学习仍保留，使用源码仓库路线。

1. 在本课程根设完整JDK21；运行./gradlew :c00-02-values-lab:run看真实调用，Windows改用gradlew.bat。
2. 打开下方完整调用端与test/MoneyTest.java，预测正常、边界、异常结果。作者源码是标准解；学习者占位副本才是练习起点。
3. 填写src/labs/foundation/Money.java的作答区；每完成一个方法运行./gradlew :c00-02-values-lab:test，先看到最小失败，再修复，不删断言。
4. 新增一条与本页易错点不同的回归。工具缺失记INVALID_ENV，没运行记NOT_RUN，不能用静态解析代替真实运行。
5. 提交源码阅读/观察表与本页迁移练习。A为自动契约，O为解释/观察，R为真实源码，T为显式教学子集；A绿不代表O/R或独立掌握完成。

主线JDK21、Gradle8.10.2、JUnit5.11.4，无前端/Docker/外部服务。测试限定合成输入和临时目录，不访问真实业务数据。

## 完整调用示例

```java
package labs.foundation;

public final class MoneyUsage {
    public static void main(String[] args) {
        System.out.println("银行家舍入=" + Money.of("1.015"));
        System.out.println("订单金额=" + Money.of("10.00").plus(Money.of("2.50")));
    }
}
```

## 可选提示

<div class="hint" title="H1：合同与不变量">把正常、边界、异常与失败后状态分别列出，先判断哪条可见测试在区分它们。</div>
<div class="hint" title="H2：最小反例">先从本页机制解释找到一个两三项输入的反例，避免直接加随机压力掩盖错误。</div>
<div class="hint" title="H3：步骤定位">沿下面标准解的步骤检查第一次状态偏离，再决定改哪一段；答案无需先过题即可查看。</div>

## 标准解与逐步解释

[完整实现副本](solutions/Money.java.txt)。以下是同一源码的完整内容；common、辅助类、调用端和全部测试均公开。

```java
package labs.foundation;

import java.math.*;
import java.util.*;

public final class Money implements Comparable<Money> {
    private final BigDecimal amount;

    private Money(BigDecimal amount) {
        this.amount = amount;
    }

    public static Money of(String decimal) {
        // 作答开始
        BigDecimal raw = new BigDecimal(Objects.requireNonNull(decimal, "金额文本不能为空"));
        if (raw.signum() < 0) throw new IllegalArgumentException("金额不能为负");
        BigDecimal normalized = raw.setScale(2, RoundingMode.HALF_EVEN);
        normalized.unscaledValue().longValueExact();
        return new Money(normalized);
        // 作答结束
    }

    public Money plus(Money other) {
        return of(amount.add(Objects.requireNonNull(other).amount).toPlainString());
    }

    public Money times(BigDecimal factor) {
        if (Objects.requireNonNull(factor).signum() < 0) throw new IllegalArgumentException("乘数非负");
        return of(amount.multiply(factor).toPlainString());
    }

    public long cents() {
        return amount.unscaledValue().longValueExact();
    }

    @Override
    public int compareTo(Money other) {
        return amount.compareTo(Objects.requireNonNull(other).amount);
    }

    @Override
    public boolean equals(Object other) {
        return other instanceof Money that && amount.equals(that.amount);
    }

    @Override
    public int hashCode() {
        return amount.hashCode();
    }

    @Override
    public String toString() {
        return amount.toPlainString();
    }

    public record OrderId(String value) {
        public OrderId {
            value = Objects.requireNonNull(value, "ID不能为空").strip();
            if (value.isEmpty() || value.length() > 64)
                throw new IllegalArgumentException("ID长度须为1至64");
        }
    }
}
```

1. 用字符串构造避免二进制浮点已带来的误差；不是把new BigDecimal(double)的结果“事后修一下”就消失。
2. 先检查raw.signum，再舍入，避免负极小数被舍成0后逃过约束。setScale明确业务舍入选择；HALF_EVEN只是本题合同，不代表所有金融场景都该这样。
3. unscaledValue().longValueExact把分值范围检查和精确转换合在一起。BigDecimal本身任意精度不意味着本系统long接口无限范围。
4. equals对规范化BigDecimal安全；一般BigDecimal.equals比较scale而compareTo按数值比较，测试给出1.0/1.00反例。Money不可变但OrderId是另一种领域值。
5. 复杂度依赖十进制位数，不说所有BigDecimal运算O(1)。可接受替代用movePointRight(2).longValueExact校验。

## 源码与证据

[OpenJDK21固定源文件](https://github.com/openjdk/jdk/blob/890adb6410dab4606a4f26a942aed02fb2f55387/src/java.base/share/classes/java/math/BigDecimal.java)，tag jdk-21+35，commit 890adb6410dab4606a4f26a942aed02fb2f55387。符号：setScale、compareTo、equals、longValueExact。

记录scale、precision、舍入模式与结果，说明API合同和具体存储优化不是同一层。

R记录必须含版本/SHA、文件/符号、输入、关键状态、分支、反例与结论。当前补丁JDK的src.zip不是GA原件，动态证据必须分别标识，不能编造断点截图。[源码路线与证据模板](../../../docs/源码与评阅.md)说明如何核对。教学容器只实现已列子集，不称生产级框架。

## 面试问答与迁移

问：compareTo相等却equals不等会影响什么？答：TreeMap按比较器判等、HashMap按equals/hashCode，可能容纳不同数量的键。
问：Integer==为何危险？答：比较引用受缓存/装箱影响，业务应按值比较；null自动拆箱会NPE。本课不依赖缓存上界。
问：String不可变等于两个相同文本是同一对象？答：不是，new String反例说明身份与值分离。
迁移：把舍入合同改为HALF_UP并解释哪些测试必须改变；在国际币种新增不同最小单位时不要硬编码“都两位”。

## 完成标准

关键A全部通过；解释、证据、迁移按[评阅标准](../../../docs/源码与评阅.md)至少达到能讲机制和边界。记录H0独立到H4完整答案、首次失败、修复原因，并在24小时后不看答案完成变式。不能用“看懂了/复制后全绿”代替独立掌握，也不承诺面试结果。
