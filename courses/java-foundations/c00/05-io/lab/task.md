# C00-05 · UTF-8文件、资源关闭与失败链

## 企业场景与进入条件

批处理要读取中文文件并输出可重现报表，异常路径同样必须关闭资源。先修解析与异常；150分钟。示例张三两笔120和80输出张三|200。

## 合同、输入输出与修改范围

显式UTF-8；report只接收沙箱目录内直接文件名，拒绝路径跳出、符号链接与同一输入输出。summarize接管Reader/Writer并关闭，空文件输出空，坏行在任何写入前失败。成功按客户自然顺序输出，换行固定\n。直接Reader输入须为课程合成的小文件，不拿真实用户文件测试。

本题在独立完整工程中运行：src是实现与调用方，test是全部公开测试，common是本课程内的完整领域checkpoint。只改答案区，接口和测试合同不变；可在test补自己的回归。标准解始终直接可读，未隐藏测试或答案。

## 概念与ASCII图

```text
UTF-8文件 -> Reader -> 全部解析/校验 -> 有序汇总 -> Writer
               |                                |
               +-------- try-with-resources ----+
业务异常主因 + close异常suppressed，不覆盖根因
```

## 分步使用与验证

运行路线先区分：以下./gradlew命令适用于带Wrapper的源码仓库课程目录。若从Academy官方ZIP导入，用本题Check、Usage main运行按钮或IDE Gradle工具窗口的对应任务；Academy2026.9官方ZIP实际会剔除Wrapper脚本和JAR，不能承诺导入目录的终端./gradlew可用。完整CLI学习仍保留，使用源码仓库路线。

1. 在本课程根设完整JDK21；运行./gradlew :c00-05-io-lab:run看真实调用，Windows改用gradlew.bat。
2. 打开下方完整调用端与test/OrderFilesTest.java，预测正常、边界、异常结果。作者源码是标准解；学习者占位副本才是练习起点。
3. 填写src/labs/foundation/OrderFiles.java的作答区；每完成一个方法运行./gradlew :c00-05-io-lab:test，先看到最小失败，再修复，不删断言。
4. 新增一条与本页易错点不同的回归。工具缺失记INVALID_ENV，没运行记NOT_RUN，不能用静态解析代替真实运行。
5. 提交源码阅读/观察表与本页迁移练习。A为自动契约，O为解释/观察，R为真实源码，T为显式教学子集；A绿不代表O/R或独立掌握完成。

主线JDK21、Gradle8.10.2、JUnit5.11.4，无前端/Docker/外部服务。测试限定合成输入和临时目录，不访问真实业务数据。

## 完整调用示例

```java
package labs.foundation;

public final class OrderFilesUsage {
    public static void main(String[] args) throws Exception {
        var out = new java.io.StringWriter();
        OrderFiles.summarize(new java.io.StringReader("A|张三|120|PAID\nB|张三|80|PAID"), out);
        System.out.print("报告：\n" + out);
    }
}
```

## 可选提示

<div class="hint" title="H1：合同与不变量">把正常、边界、异常与失败后状态分别列出，先判断哪条可见测试在区分它们。</div>
<div class="hint" title="H2：最小反例">先从本页机制解释找到一个两三项输入的反例，避免直接加随机压力掩盖错误。</div>
<div class="hint" title="H3：步骤定位">沿下面标准解的步骤检查第一次状态偏离，再决定改哪一段；答案无需先过题即可查看。</div>

## 标准解与逐步解释

[完整实现副本](solutions/OrderFiles.java.txt)。以下是同一源码的完整内容；common、辅助类、调用端和全部测试均公开。

```java
package labs.foundation;

import java.io.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.util.*;

public final class OrderFiles {
    private OrderFiles() {}

    public static void summarize(Reader input, Writer output) throws IOException {
        // 作答开始
        try (BufferedReader reader = new BufferedReader(Objects.requireNonNull(input));
                Writer writer = Objects.requireNonNull(output)) {
            List<String> lines = new ArrayList<>();
            String line;
            while ((line = reader.readLine()) != null) {
                if (lines.size() == 10000) throw new IOException("文件超过10000行");
                lines.add(line);
            }
            Map<String, Long> totals = new TreeMap<>();
            for (Order o : OrderCodec.parseBatch(lines))
                if (o.status() == Order.Status.PAID)
                    totals.merge(o.customer(), o.cents(), Math::addExact);
            for (var entry : totals.entrySet())
                writer.write(entry.getKey() + "|" + entry.getValue() + "\n");
        }
        // 作答结束
    }

    public static void report(Path directory, String inputName, String outputName)
            throws IOException {
        Path in = child(directory, inputName), out = child(directory, outputName);
        if (in.equals(out)) throw new IllegalArgumentException("输入输出不得相同");
        try (Reader input = Files.newBufferedReader(in, StandardCharsets.UTF_8)) {
            summarize(input, Files.newBufferedWriter(out, StandardCharsets.UTF_8));
        }
    }

    private static Path child(Path directory, String name) {
        Objects.requireNonNull(directory);
        Objects.requireNonNull(name);
        if (!name.matches("[A-Za-z0-9._-]+") || name.equals(".") || name.equals(".."))
            throw new IllegalArgumentException("只允许沙箱内直接文件名");
        Path path = directory.resolve(name);
        if (Files.isSymbolicLink(path)) throw new IllegalArgumentException("实验不跟随符号链接");
        return path;
    }
}
```

1. 先读并验证整批，再输出，保证解析错误不产生部分报表；写入IO失败仍可能留下部分文件，本课没有宣称崩溃原子替换。
2. try-with-resources按逆序关闭，业务异常保留为主，关闭异常加入suppressed。测试用明确的假Reader/Writer使两次close都失败，核实主异常与两条副异常。
3. 指定UTF-8不依赖平台默认编码。字符串Writer便于测试完整调用，不需要造隐藏文件或读用户主目录。
4. 文件名校验是本地实验围栏，不是多租户文件系统沙箱；并发攻击/符号链接替换需要更强机制。N行驻留，空间O(N)，最多10000行；生产大文件应改流式校验/临时文件策略。

## 源码与证据

[OpenJDK21固定源文件](https://github.com/openjdk/jdk/blob/890adb6410dab4606a4f26a942aed02fb2f55387/src/java.base/share/classes/java/io/BufferedReader.java)，tag jdk-21+35，commit 890adb6410dab4606a4f26a942aed02fb2f55387。符号：readLine、close；JLS21 try-with-resources。

库负责字符/流生命周期；suppressed的语言翻译规则看JLS14.20.3，不能只读某个类推断全部异常语义。

R记录必须含版本/SHA、文件/符号、输入、关键状态、分支、反例与结论。当前补丁JDK的src.zip不是GA原件，动态证据必须分别标识，不能编造断点截图。[源码路线与证据模板](../../../docs/源码与评阅.md)说明如何核对。教学容器只实现已列子集，不称生产级框架。

## 面试问答与迁移

问：finally里throw close异常有什么问题？答：覆盖最初业务异常，排障会盯错原因；查看DebugRepairs的独立反例。
问：资源关闭成功证明文件写入耐久吗？答：不能，flush/close与文件系统/磁盘持久性不是一个保证。
问：无BOM的中文文件乱码先查什么？答：实际编码与明确使用的解码器，不先改业务代码。
迁移：输出改为临时文件+原子移动，说明跨文件系统、失败清理和覆盖原文件的风险边界。

## 完成标准

关键A全部通过；解释、证据、迁移按[评阅标准](../../../docs/源码与评阅.md)至少达到能讲机制和边界。记录H0独立到H4完整答案、首次失败、修复原因，并在24小时后不看答案完成变式。不能用“看懂了/复制后全绿”代替独立掌握，也不承诺面试结果。
