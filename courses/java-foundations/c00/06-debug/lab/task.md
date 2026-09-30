# C00-06 · 三个独立缺陷的最小回归与调试

## 企业场景与进入条件

线上小修最危险的是同时改变多条语义。这里把越界、别名和异常覆盖拆成三个互不依赖的最小实验。先修数组/异常；120分钟。

## 合同、输入输出与修改范围

slice使用[from,to)，允许from=to=size；输出不可修改结构快照，拒绝越界及null元素。snapshot复制外层和每个内层列表（String元素不可变），不保留可变列表别名。withResource让操作异常为主、关闭异常suppressed；三个方法各有独立测试。

本题在独立完整工程中运行：src是实现与调用方，test是全部公开测试，common是本课程内的完整领域checkpoint。只改答案区，接口和测试合同不变；可在test补自己的回归。标准解始终直接可读，未隐藏测试或答案。

## 概念与ASCII图

```text
缺陷1: to-1 -> 丢末项       -> 半开区间边界测试
缺陷2: 只复制外层 -> 内层变  -> 修改原列表后断言
缺陷3: finally抛close -> 主因丢 -> 主/副异常身份断言
每次: 先红 -> 断点最小状态 -> 修复 -> 全回归
```

## 三个真实错误checkpoint

本节学习者起点保留三个能编译但行为错误的方法，使用TODO注释标记，区别于其他题的待实现异常。三个独立checkpoint也完整可见：[边界错误](bugs/01-boundary/DebugRepairs.java.txt)、[对象别名](bugs/02-alias/DebugRepairs.java.txt)、[异常覆盖](bugs/03-suppressed/DebugRepairs.java.txt)。每份只保留一种缺陷，另外两方法正确，便于分别设置断点。

在保留现有作答备份后，可把选中的完整checkpoint内容放到本题src/labs/foundation/DebugRepairs.java，再运行对应的halfOpenBoundary、nestedAlias或primaryAndSuppressed测试；先解释失败的变量/异常链，再修复。所有错误checkpoint都由公开测试实际击杀，不是只有错误描述的占位文件。

## 分步使用与验证

运行路线先区分：以下./gradlew命令适用于带Wrapper的源码仓库课程目录。若从Academy官方ZIP导入，用本题Check、Usage main运行按钮或IDE Gradle工具窗口的对应任务；Academy2026.9官方ZIP实际会剔除Wrapper脚本和JAR，不能承诺导入目录的终端./gradlew可用。完整CLI学习仍保留，使用源码仓库路线。

1. 在本课程根设完整JDK21；运行./gradlew :c00-06-debug-lab:run看真实调用，Windows改用gradlew.bat。
2. 打开下方完整调用端与test/DebugRepairsTest.java，预测正常、边界、异常结果。作者源码是标准解；学习者占位副本才是练习起点。
3. 填写src/labs/foundation/DebugRepairs.java的作答区；每完成一个方法运行./gradlew :c00-06-debug-lab:test，先看到最小失败，再修复，不删断言。
4. 新增一条与本页易错点不同的回归。工具缺失记INVALID_ENV，没运行记NOT_RUN，不能用静态解析代替真实运行。
5. 提交源码阅读/观察表与本页迁移练习。A为自动契约，O为解释/观察，R为真实源码，T为显式教学子集；A绿不代表O/R或独立掌握完成。

主线JDK21、Gradle8.10.2、JUnit5.11.4，无前端/Docker/外部服务。测试限定合成输入和临时目录，不访问真实业务数据。

## 完整调用示例

```java
package labs.foundation;

public final class DebugRepairsUsage {
    public static void main(String[] args) throws Exception {
        System.out.println("半开区间=" + DebugRepairs.slice(java.util.List.of("A", "B"), 1, 2));
        System.out.println(
                "资源执行=" + DebugRepairs.withResource(() -> System.out.println("资源关闭"), () -> "完成"));
    }
}
```

## 可选提示

<div class="hint" title="H1：合同与不变量">把正常、边界、异常与失败后状态分别列出，先判断哪条可见测试在区分它们。</div>
<div class="hint" title="H2：最小反例">先从本页机制解释找到一个两三项输入的反例，避免直接加随机压力掩盖错误。</div>
<div class="hint" title="H3：步骤定位">沿下面标准解的步骤检查第一次状态偏离，再决定改哪一段；答案无需先过题即可查看。</div>

## 标准解与逐步解释

[完整实现副本](solutions/DebugRepairs.java.txt)。以下是同一源码的完整内容；common、辅助类、调用端和全部测试均公开。

```java
package labs.foundation;

import java.util.*;
import java.util.concurrent.Callable;

public final class DebugRepairs {
    private DebugRepairs() {}

    public static <T> List<T> slice(List<T> values, int from, int to) {
        // 作答开始
        Objects.checkFromToIndex(from, to, values.size());
        return List.copyOf(values.subList(from, to));
        // 作答结束
    }

    public static List<List<String>> snapshot(List<List<String>> values) {
        // 作答开始
        return values.stream().map(List::copyOf).toList();
        // 作答结束
    }

    public static <T> T withResource(AutoCloseable resource, Callable<T> operation)
            throws Exception {
        // 作答开始
        try (resource) {
            return operation.call();
        }
        // 作答结束
    }
}
```

1. 区间不变量是0<=from<=to<=size，终点独占；先Objects.checkFromToIndex避免自己写错边界。
2. List.copyOf(outer)仅复制外层，内层ArrayList仍是同一对象；逐行copyOf才能隔离结构。本题String不可变使此层复制足够，但换成可变Order还需重新定义深度。
3. try(resource)保持原始异常对象，关闭失败通过getSuppressed访问。测试用assertSame检查因果信息没有被包装覆盖。
4. 三种已知错误实现分别是subList(from,to-1)、只copyOf外层、finally直接close。作者验证分别击杀，不用扩大超时或改断言规避。复杂度slice O(区间长度)、snapshot O(总元素)、资源包装O(1)额外开销。

## 源码与证据

[OpenJDK21固定源文件](https://github.com/openjdk/jdk/blob/890adb6410dab4606a4f26a942aed02fb2f55387/src/java.base/share/classes/java/util/Objects.java)，tag jdk-21+35，commit 890adb6410dab4606a4f26a942aed02fb2f55387。符号：checkFromToIndex；Throwable.addSuppressed/getSuppressed。

记录from/to/size和异常身份；源码阅读辅助推断，自己的断点结果单独留档。

R记录必须含版本/SHA、文件/符号、输入、关键状态、分支、反例与结论。当前补丁JDK的src.zip不是GA原件，动态证据必须分别标识，不能编造断点截图。[源码路线与证据模板](../../../docs/源码与评阅.md)说明如何核对。教学容器只实现已列子集，不称生产级框架。

## 面试问答与迁移

问：断点看到变量“不对”就够吗？答：还需说明输入、预期不变量、第一次偏离位置与修复后回归。
问：不可修改列表一定不会变化？答：视图可能随源变化，元素本身也可能可变；说明哪一层不可变。
问：异常包装何时合理？答：增加调用层上下文并保留cause时合理；把根异常丢掉不是。
迁移：给snapshot加入null内层的明确政策，先写反例再改方法。

## 完成标准

关键A全部通过；解释、证据、迁移按[评阅标准](../../../docs/源码与评阅.md)至少达到能讲机制和边界。记录H0独立到H4完整答案、首次失败、修复原因，并在24小时后不看答案完成变式。不能用“看懂了/复制后全绿”代替独立掌握，也不承诺面试结果。
