# C00-01 · 可重复工作区与首次失败回归

## 企业场景与进入条件

订单团队接手旧服务，首先需要能独立构建、运行、看懂失败。先修无；90分钟。正常样例为一笔150分PAID，输出150；空批次为0。

## 合同、输入输出与修改范围

paidTotal只累计PAID，列表/元素非null，Order构造保证金额非负。long累计溢出必须ArithmeticException，不能静默回绕。不修改输入。先运行Usage，再让一条断言故意失败并恢复；任务要练的是识别失败层，而不是复制按钮。

本题在独立完整工程中运行：src是实现与调用方，test是全部公开测试，common是本课程内的完整领域checkpoint。只改答案区，接口和测试合同不变；可在test补自己的回归。标准解始终直接可读，未隐藏测试或答案。

## 概念与ASCII图

```text
源码.java -> javac --release21 -> .class -> JDK21运行
                         |
                         +-> JUnit公开断言 -> 失败定位
IDE运行JDK / 项目SDK / Gradle JVM / 测试JVM：分别记录
```

## 分步使用与验证

运行路线先区分：以下./gradlew命令适用于带Wrapper的源码仓库课程目录。若从Academy官方ZIP导入，用本题Check、Usage main运行按钮或IDE Gradle工具窗口的对应任务；Academy2026.9官方ZIP实际会剔除Wrapper脚本和JAR，不能承诺导入目录的终端./gradlew可用。完整CLI学习仍保留，使用源码仓库路线。

1. 在本课程根设完整JDK21；运行./gradlew :c00-01-workspace-lab:run看真实调用，Windows改用gradlew.bat。
2. 打开下方完整调用端与test/WorkspaceTest.java，预测正常、边界、异常结果。作者源码是标准解；学习者占位副本才是练习起点。
3. 填写src/labs/foundation/Workspace.java的作答区；每完成一个方法运行./gradlew :c00-01-workspace-lab:test，先看到最小失败，再修复，不删断言。
4. 新增一条与本页易错点不同的回归。工具缺失记INVALID_ENV，没运行记NOT_RUN，不能用静态解析代替真实运行。
5. 提交源码阅读/观察表与本页迁移练习。A为自动契约，O为解释/观察，R为真实源码，T为显式教学子集；A绿不代表O/R或独立掌握完成。

主线JDK21、Gradle8.10.2、JUnit5.11.4，无前端/Docker/外部服务。测试限定合成输入和临时目录，不访问真实业务数据。

## 完整调用示例

```java
package labs.foundation;

public final class WorkspaceUsage {
    public static void main(String[] args) {
        System.out.println(
                "已付款总分="
                        + Workspace.paidTotal(
                                java.util.List.of(new Order("A", "客户甲", 150, Order.Status.PAID))));
        System.out.println("测试运行JDK=" + Runtime.version());
    }
}
```

## 可选提示

<div class="hint" title="H1：合同与不变量">把正常、边界、异常与失败后状态分别列出，先判断哪条可见测试在区分它们。</div>
<div class="hint" title="H2：最小反例">先从本页机制解释找到一个两三项输入的反例，避免直接加随机压力掩盖错误。</div>
<div class="hint" title="H3：步骤定位">沿下面标准解的步骤检查第一次状态偏离，再决定改哪一段；答案无需先过题即可查看。</div>

## 标准解与逐步解释

[完整实现副本](solutions/Workspace.java.txt)。以下是同一源码的完整内容；common、辅助类、调用端和全部测试均公开。

```java
package labs.foundation;

import java.util.*;

public final class Workspace {
    private Workspace() {}

    public static long paidTotal(List<Order> orders) {
        // 作答开始
        Objects.requireNonNull(orders, "订单列表不能为空");
        long sum = 0;
        for (Order order : orders)
            if (Objects.requireNonNull(order, "订单不能为空").status() == Order.Status.PAID)
                sum = Math.addExact(sum, order.cents());
        return sum;
        // 作答结束
    }
}
```

1. 先校验容器，再逐条解引用；空列表无需特殊分支自然返回0。
2. 构造Order时拒绝非法领域值，累计器仍负责null边界与算术溢出。Math.addExact给出可观测异常，不能靠最后sum<0猜所有溢出。
3. O(N)时间、O(1)附加空间；索引for与foreach均接受。测试失败是运行期断言不满足，编译失败是类型/语法不成立，依赖下载失败属于环境。
4. IDE中先确认项目SDK与Gradle JVM都是21，设置Workspace.paidTotal行断点，观察sum从0到150，保留实际断点证据；没有截图不得写完成。

## 源码与证据

[OpenJDK21固定源文件](https://github.com/openjdk/jdk/blob/890adb6410dab4606a4f26a942aed02fb2f55387/src/java.base/share/classes/java/lang/Math.java)，tag jdk-21+35，commit 890adb6410dab4606a4f26a942aed02fb2f55387。符号：Math.addExact(long,long)。

操作数符号、结果符号与溢出分支；正常最大值+0和溢出最大值+1并列记录。

R记录必须含版本/SHA、文件/符号、输入、关键状态、分支、反例与结论。当前补丁JDK的src.zip不是GA原件，动态证据必须分别标识，不能编造断点截图。[源码路线与证据模板](../../../docs/源码与评阅.md)说明如何核对。教学容器只实现已列子集，不称生产级框架。

## 面试问答与迁移

问：绿色编译等于业务正确？答：只说明被编译器接受，漏计PENDING规则仍可能编译。追问：哪条测试击杀普通加法？Long.MAX_VALUE加1。
问：为什么不把金额先转double？答：整数分合同不需要浮点误差，转换会丢精度。
问：IDE显示21能证明Gradle也21？答：不能，各JVM配置分别看实际版本。
迁移：新增REFUNDED状态，先写过滤合同和测试再修改聚合；不通过删测试实现“通过”。

## 完成标准

关键A全部通过；解释、证据、迁移按[评阅标准](../../../docs/源码与评阅.md)至少达到能讲机制和边界。记录H0独立到H4完整答案、首次失败、修复原因，并在24小时后不看答案完成变式。不能用“看懂了/复制后全绿”代替独立掌握，也不承诺面试结果。
