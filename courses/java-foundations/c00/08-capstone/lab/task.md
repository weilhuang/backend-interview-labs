# C00-08 · 可交付的订单分析CLI

## 企业场景与进入条件

完成一个别人能调用的CLI，比写孤立方法多了输入边界、错误码、去重政策和稳定输出。先修整个C00；180分钟。

## 合同、输入输出与修改范围

每行仍按严格字段合同解析，但ID去重采用首次出现获胜，先去重再按状态过滤；重复行也必须先合法解析，不能借重复跳过坏金额。最多10000行；CLI文件最多1MiB。输出客户|总分|笔数及按客户排序的行。退出码0成功、2参数个数、3文件IO、4输入/金额错误。

本题在独立完整工程中运行：src是实现与调用方，test是全部公开测试，common是本课程内的完整领域checkpoint。只改答案区，接口和测试合同不变；可在test补自己的回归。标准解始终直接可读，未隐藏测试或答案。

## 概念与ASCII图

```text
UTF-8输入 -> 每行校验 -> 首次ID保留 -> 状态过滤
                                      |
                                      v
                              分组精确求和/计数 -> 稳定文本
参数/IO/业务错误 -> 独立错误码 -> stderr
```

## 分步使用与验证

运行路线先区分：以下./gradlew命令适用于带Wrapper的源码仓库课程目录。若从Academy官方ZIP导入，用本题Check、Usage main运行按钮或IDE Gradle工具窗口的对应任务；Academy2026.9官方ZIP实际会剔除Wrapper脚本和JAR，不能承诺导入目录的终端./gradlew可用。完整CLI学习仍保留，使用源码仓库路线。

1. 在本课程根设完整JDK21；运行./gradlew :c00-08-capstone-lab:run看真实调用，Windows改用gradlew.bat。
2. 打开下方完整调用端与test/OrderAnalyzerTest.java，预测正常、边界、异常结果。作者源码是标准解；学习者占位副本才是练习起点。
3. 填写src/labs/foundation/OrderAnalyzer.java的作答区；每完成一个方法运行./gradlew :c00-08-capstone-lab:test，先看到最小失败，再修复，不删断言。
4. 新增一条与本页易错点不同的回归。工具缺失记INVALID_ENV，没运行记NOT_RUN，不能用静态解析代替真实运行。
5. 提交源码阅读/观察表与本页迁移练习。A为自动契约，O为解释/观察，R为真实源码，T为显式教学子集；A绿不代表O/R或独立掌握完成。

主线JDK21、Gradle8.10.2、JUnit5.11.4，无前端/Docker/外部服务。测试限定合成输入和临时目录，不访问真实业务数据。

额外真实CLI：课程根运行./gradlew :c00-08-capstone-lab:cli，读取fixtures/orders.txt；用-PinputFile=fixtures/invalid-orders.txt观察行号错误和非零退出，用-Pstatus=PENDING改变筛选。这些都是课程内合成文件。

## 完整调用示例

```java
package labs.foundation;

public final class OrderAnalyzerUsage {
    public static void main(String[] args) {
        System.out.print(
                OrderAnalyzer.analyze(
                        java.util.List.of("A|张三|120|PAID", "B|张三|80|PAID", "A|张三|999|PAID"),
                        Order.Status.PAID));
    }
}
```

## 可选提示

<div class="hint" title="H1：合同与不变量">把正常、边界、异常与失败后状态分别列出，先判断哪条可见测试在区分它们。</div>
<div class="hint" title="H2：最小反例">先从本页机制解释找到一个两三项输入的反例，避免直接加随机压力掩盖错误。</div>
<div class="hint" title="H3：步骤定位">沿下面标准解的步骤检查第一次状态偏离，再决定改哪一段；答案无需先过题即可查看。</div>

## 标准解与逐步解释

[完整实现副本](solutions/OrderAnalyzer.java.txt)。以下是同一源码的完整内容；common、辅助类、调用端和全部测试均公开。

```java
package labs.foundation;

import java.io.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.util.*;

public final class OrderAnalyzer {
    private OrderAnalyzer() {}

    public static String analyze(List<String> lines, Order.Status status) {
        // 作答开始
        Objects.requireNonNull(lines);
        Objects.requireNonNull(status);
        if (lines.size() > 10000) throw new IllegalArgumentException("最多10000行");
        Map<String, Order> unique = new LinkedHashMap<>();
        for (int i = 0; i < lines.size(); i++) {
            Order order = OrderCodec.parse(lines.get(i), i + 1);
            unique.putIfAbsent(order.id(), order);
        }
        Map<String, Long> totals = new TreeMap<>();
        Map<String, Integer> count = new TreeMap<>();
        for (Order order : unique.values())
            if (order.status() == status) {
                totals.merge(order.customer(), order.cents(), Math::addExact);
                count.merge(order.customer(), 1, Integer::sum);
            }
        StringBuilder output = new StringBuilder("客户|总分|笔数\n");
        for (String customer : totals.keySet())
            output.append(customer)
                    .append('|')
                    .append(totals.get(customer))
                    .append('|')
                    .append(count.get(customer))
                    .append('\n');
        return output.toString();
        // 作答结束
    }

    public static int run(String[] args, PrintStream out, PrintStream error) {
        if (args.length != 2) {
            error.println("用法：文件路径 PAID或PENDING；只使用你创建的合成输入");
            return 2;
        }
        try {
            Order.Status status = Order.Status.valueOf(args[1]);
            Path input = Path.of(args[0]);
            if (Files.size(input) > 1024 * 1024) throw new IOException("文件超过1MiB");
            out.print(analyze(Files.readAllLines(input, StandardCharsets.UTF_8), status));
            return 0;
        } catch (IOException e) {
            error.println("文件错误：" + e.getMessage());
            return 3;
        } catch (IllegalArgumentException | ArithmeticException e) {
            error.println("输入错误：" + e.getMessage());
            return 4;
        }
    }

    public static void main(String[] args) {
        System.exit(run(args, System.out, System.err));
    }
}
```

1. 去重和过滤顺序是业务合同：A先PENDING后PAID仍保留第一笔，过滤后不会突然变PAID。测试刻意构造这个反例。
2. 即使重复ID，仍先解析整行，避免损坏数据静默掩盖。sum采用addExact，出现大金额必须失败。
3. analyze纯函数便于测试；run注入out/error且返回退出码，main只做System.exit边界，JUnit不用拦截虚拟机退出。
4. TreeMap保证客户顺序，固定换行和字段格式保证同输入可复现。整体O(N+U log U)，保存去重数据O(N)；这里没有声称流式无限输入。
5. 可接受替代用TreeMap存ID，只要first-wins与最终客户排序不变；ID容器顺序本来不是输出合同。

## 源码与证据

[OpenJDK21固定源文件](https://github.com/openjdk/jdk/blob/890adb6410dab4606a4f26a942aed02fb2f55387/src/java.base/share/classes/java/util/Map.java)，tag jdk-21+35，commit 890adb6410dab4606a4f26a942aed02fb2f55387。符号：putIfAbsent；LinkedHashMap插入顺序；TreeMap比较顺序。

分别解释去重语义、内部顺序和最终输出顺序，不把某次HashMap遍历当协议。

R记录必须含版本/SHA、文件/符号、输入、关键状态、分支、反例与结论。当前补丁JDK的src.zip不是GA原件，动态证据必须分别标识，不能编造断点截图。[源码路线与证据模板](../../../docs/源码与评阅.md)说明如何核对。教学容器只实现已列子集，不称生产级框架。

## 面试问答与迁移

问：first-wins等于生产幂等吗？答：这里只是单次文件去重，不覆盖跨进程持久化、并发事务或重试业务效果。
问：错误时stdout部分输出怎么办？答：当前解析汇总后再print，但底层输出故障不保证事务原子性；需要更强交付机制另设计。
问：参数非法为何不能都返回0？答：调用脚本会误认为成功，错误码是可自动使用的接口。
迁移：新增最低金额过滤，说明它在去重前还是后，并通过CLI端到端测试锁定。

## 完成标准

关键A全部通过；解释、证据、迁移按[评阅标准](../../../docs/源码与评阅.md)至少达到能讲机制和边界。记录H0独立到H4完整答案、首次失败、修复原因，并在24小时后不看答案完成变式。不能用“看懂了/复制后全绿”代替独立掌握，也不承诺面试结果。
