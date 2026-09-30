# C03-07 · Java25及后续版本的隔离阅读与验证

## 企业场景与进入条件

平台升级评审需要知道“从哪一版开始、目标版是什么状态、需要哪些开关、哪里已移除”。把博客摘要直接抄进依赖要求会让主线课程和生产构建同时失真。本节维护版本快照而非追逐“最新版”。预计120分钟。

## 可执行目标与合同

FeatureGate是T教学规则模型，不是JDK真实能力探测器。compileFlags要求编译器主版本等于feature.targetRelease，FINAL只加--release，PREVIEW额外--enable-preview，INCUBATOR额外--add-modules与明确模块名，REMOVED拒绝；结果不可修改。firstRelease表示该特性谱系最早出现（可能预览/孵化），不表示当时稳定。

A测试在JDK21验证规则模型，R/O通过官方资料核对版本状态，这些构成本节主线。experiments/java25下的Compact、ModuleImports、ScopedDemo、PrimitivePatterns、VectorDemo只是显式版本对照资料附录，主线Gradle完全不包含它们。只有已经拥有完整JDK25且自愿验证时，才指定JAVA25_HOME并运行python scripts/version25.py，另观察预览/孵化缺开关反例。没有25环境直接跳过，脚本输出NOT_RUN并退出3；这不影响V1毕业，不要求另装或下载任何JDK，脚本也不会自动下载或安装。不能拿JDK21测试通过代替实际25编译结果。

分类：A为公开契约与资源回归；O为运行观察与解释；R为固定真实源码阅读；T为显式缩小的教学模型。测试通过不意味着O/R完成。JDK21为主线，Gradle8.10.2、JUnit5.11.4；无前端、无Docker、无真实业务数据。

## 机制图解

```text
目标JDK版本 -> 官方JEP Release/Status -> 发布说明/迁移指南
                       |
                       v
            FINAL / PREVIEW / INCUBATOR / REMOVED
                       |
                       v
          自选附录：已有25时编译/运行/缺开关反例
                       |
            +----------+----------+
            v                     v
          PASS                 NOT_RUN/FAIL

主线JDK21 <不继承附录开关> 25资料目录（运行可跳过）
```

## 编码与验证步骤

1. 在课程根运行python scripts/lab.py doctor，确认完整JDK21。缺环境记INVALID_ENV，不判断知识水平。
2. 打开本题src与test全部文件，先运行调用端、读成功与失败样例。作者源码是完整解；学习者副本占位区才是待实现区域，答案也直接在本页下方。
3. 只修改答案区，保持公开合同。先运行本题测试，再补边界/异常测试；不要改掉断言消灭失败。
4. 课程根运行./gradlew :jvm-07-java25-lab:test 与 :jvm-07-java25-lab:run。Windows使用gradlew.bat。首次联网下载依赖与编码错误分开处理。
5. 观察入口：python scripts/lab.py usage。记录JDK完整版本、命令、输入、预期、实际和边界。新证据输出build/evidence，不覆盖此前结果。

## 完整调用示例

以下调用端文件、src下辅助类、test下所有测试均对学习者可见；没有隐藏评分逻辑。

```java
package labs.jvm;

public final class FeatureGateUsage {
    public static void main(String[] args) {
        for (var f : FeatureGate.jdk25Matrix())
            System.out.println(f.name() + "：" + f.state() + "，目标=" + f.targetRelease());
        System.out.println("JDK25为自选资料附录：已有环境才运行 scripts/version25.py；否则NOT_RUN，不影响毕业");
    }
}
```

## 渐进提示（可选，不锁答案）

<div class="hint" title="H1：先明确不变量">把合同拆为正常、边界、异常、清理四类，先找哪个可见测试证明当前机制。</div>
<div class="hint" title="H2：用最小反例">比较本题说明中的易错边界与完整测试；写一个能区分两种实现的最小输入。</div>
<div class="hint" title="H3：对照步骤">按下面标准解的逐步解释检查状态变化，先定位错误层，再决定是否重写。</div>

## 标准解与逐步解释

[可单独打开完整标准解](solutions/FeatureGate.java.txt)。同一实现也在这里完整展示，无须切分支、解锁或先通过题目。

```java
package labs.jvm;

import java.util.*;

public final class FeatureGate {
    public enum State {
        FINAL,
        PREVIEW,
        INCUBATOR,
        REMOVED
    }

    public record Feature(
            String name, int firstRelease, int targetRelease, State state, String module) {
        public Feature {
            Objects.requireNonNull(name);
            Objects.requireNonNull(state);
            if (firstRelease < 1 || targetRelease < firstRelease)
                throw new IllegalArgumentException("版本区间非法");
        }
    }

    private FeatureGate() {}

    public static List<String> compileFlags(Feature feature, int compilerRelease) {
        // 作答开始
        Objects.requireNonNull(feature);
        if (compilerRelease != feature.targetRelease())
            throw new IllegalArgumentException("必须使用目标版本编译器复核");
        if (feature.state() == State.REMOVED) throw new IllegalStateException("已移除，不能靠编译开关恢复");
        List<String> flags =
                new ArrayList<>(List.of("--release", Integer.toString(compilerRelease)));
        if (feature.state() == State.PREVIEW) flags.add("--enable-preview");
        if (feature.state() == State.INCUBATOR) {
            flags.add("--add-modules");
            flags.add(Objects.requireNonNull(feature.module()));
        }
        return List.copyOf(flags);
        // 作答结束
    }

    public static List<Feature> jdk25Matrix() {
        return List.of(
                new Feature("record patterns", 19, 25, State.FINAL, null),
                new Feature("module imports", 23, 25, State.FINAL, null),
                new Feature("compact source files", 21, 25, State.FINAL, null),
                new Feature("scoped values", 20, 25, State.FINAL, null),
                new Feature("structured concurrency", 19, 25, State.PREVIEW, null),
                new Feature("primitive patterns", 23, 25, State.PREVIEW, null),
                new Feature("vector API", 16, 25, State.INCUBATOR, "jdk.incubator.vector"),
                new Feature("32-bit x86 port", 1, 25, State.REMOVED, null));
    }
}
```

1. 先确定“目标25”这个上下文，再解释状态。模块导入从23预览走到25正式，紧凑源文件的谱系从21预览到25正式；不能因为旧文章写preview就永久加开关。
2. JDK25正式：record patterns（21已正式）、module imports、compact source files、scoped values。结构化并发仍是第五次预览，primitive patterns是第三次预览，Vector API为第十次孵化。32位x86 port移除是平台支持变化，不是加一个javac选项能恢复的API。
3. --enable-preview必须匹配编译器当前主版本，运行预览class也需启用；--release25并不表示JDK21编译器突然获得25语法。孵化模块使用--add-modules，不应机械当预览开关。
4. 本脚本只对五个示例做真实编译；结构化并发API形状变化需另行验证，不能把21的preview代码直接视为25可编译。状态表阅读完整性与实验覆盖分开列。
5. 正式特性一般无需preview开关，但升级可能仍有二进制/行为/安全默认值/GC变化。Oracle迁移指南也区分deprecated-for-removal与removed，Applet在25不能因未来移除计划写成25已移除。
6. 模型复杂度O(1)。替代实现按State switch而不是if链同样正确。真实工程可从版本化数据源维护矩阵并记录审阅日期，不能自动从特性名字猜状态。

## 源码与证据

固定OpenJDK21 GA tag jdk-21+35，commit 890adb6410dab4606a4f26a942aed02fb2f55387。[真实源文件](https://github.com/openjdk/jdk/blob/890adb6410dab4606a4f26a942aed02fb2f55387/src/java.base/share/classes/java/lang/VirtualThread.java)；符号：JDK21 VirtualThread与JEP444；JDK25以独立矩阵来源核对。完整出处和补充规范见课程根[源码阅读清单](../../../docs/源码阅读清单.md)。

记录每个JEP编号、release、正式/预览/孵化/移除状态、查阅日期及原文链接；在report.json保留完整命令与返回码。25源码使用独立冻结tag，不能把21默认src.zip当25的实际源码。

R证据至少包含项目/版本/SHA、文件与符号、输入、关键分支、状态值、结论及反例。源码网页定位不等于已实际断点；本课程没有伪造截图。若IDE默认打开供应商补丁版源码，请另记录该版本，不冒充GA调试已完成。

## 面试问答与迁移

- 问：LTS意味着每个特性都正式吗？答：不意味着；发行支持策略与特性成熟状态是两个维度，25里仍有预览和孵化。
- 问：能用最新版javac --release21测试旧版preview吗？答：preview只面向当前编译器版本，旧preview需对应旧JDK；正式API的--release约束与preview机制不同。
- 问：孵化和预览有什么差别？答：孵化模块是非最终API的发布机制，预览是语言/JVM/API演进试用机制；具体命令按该JEP给的要求验证，不能只背一个统一开关。
- 问：源码tag、运行JDK补丁版本为何都要记录？答：GA源码锚点稳定，但供应商补丁可能有修复或回移。动态调试要匹配实际src.zip；阅读GA不能冒充当前运行补丁源码完全一致。
- 迁移：为26或之后的某一已发布版本建立新快照，逐条从官方来源更新，不改21默认编译；未安装该JDK就记录NOT_RUN。

## 完成与复盘

V1完成本节要求JDK21规则模型测试、官方状态矩阵解释与阅读迁移；25附录实际运行不列为毕业条件。无现成25环境保留NOT_RUN即可，不需补装JDK。

A必须真正通过；O/R提交证据并按根目录[评阅标准](../../../docs/评阅标准.md)评阅。记录H0独立/H1-H4提示、首次失败、改动原因、24小时后换条件回测。至少能用一个反例解释结论边界。课程不以关键词计分，也不承诺面试结果。
