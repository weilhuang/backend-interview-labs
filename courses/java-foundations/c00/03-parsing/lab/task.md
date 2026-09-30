# C00-03 · 从订单行到领域模型与定位错误

## 企业场景与进入条件

订单接入文件不能把坏金额当0，也不能丢掉错误行号。先修值对象/异常；120分钟。格式A|张三|120|PAID，四字段，金额为整数分。

## 合同、输入输出与修改范围

单行最多512字符；四字段strip后id/customer非空，cents为非负long，status精确PAID或PENDING。行号从1开始。parseBatch最多10000行，重复ID在第二次出现位置报ParseFailure，返回不可修改列表。ParseFailure保留line/field和中文原因；不允许吞异常继续默默少算。

本题在独立完整工程中运行：src是实现与调用方，test是全部公开测试，common是本课程内的完整领域checkpoint。只改答案区，接口和测试合同不变；可在test补自己的回归。标准解始终直接可读，未隐藏测试或答案。

## 概念与ASCII图

```text
原始文本 -> 字段结构 -> 字段解析 -> 领域Order
                |           |           |
                +-----------+-----------+-> 行号 + 字段 + 原因
批次 -> ID集合 -> 重复定位 -> 完整不可修改结果
```

## 分步使用与验证

运行路线先区分：以下./gradlew命令适用于带Wrapper的源码仓库课程目录。若从Academy官方ZIP导入，用本题Check、Usage main运行按钮或IDE Gradle工具窗口的对应任务；Academy2026.9官方ZIP实际会剔除Wrapper脚本和JAR，不能承诺导入目录的终端./gradlew可用。完整CLI学习仍保留，使用源码仓库路线。

1. 在本课程根设完整JDK21；运行./gradlew :c00-03-parsing-lab:run看真实调用，Windows改用gradlew.bat。
2. 打开下方完整调用端与test/OrderParserTest.java，预测正常、边界、异常结果。作者源码是标准解；学习者占位副本才是练习起点。
3. 填写src/labs/foundation/OrderParser.java的作答区；每完成一个方法运行./gradlew :c00-03-parsing-lab:test，先看到最小失败，再修复，不删断言。
4. 新增一条与本页易错点不同的回归。工具缺失记INVALID_ENV，没运行记NOT_RUN，不能用静态解析代替真实运行。
5. 提交源码阅读/观察表与本页迁移练习。A为自动契约，O为解释/观察，R为真实源码，T为显式教学子集；A绿不代表O/R或独立掌握完成。

主线JDK21、Gradle8.10.2、JUnit5.11.4，无前端/Docker/外部服务。测试限定合成输入和临时目录，不访问真实业务数据。

## 完整调用示例

```java
package labs.foundation;

public final class OrderParserUsage {
    public static void main(String[] args) {
        System.out.println(OrderParser.parseBatch(java.util.List.of(" A | 张三 | 120 | PAID ")));
        try {
            OrderParser.parse("B|甲|坏金额|PAID", 2);
        } catch (ParseFailure e) {
            System.out.println("预期错误=" + e.getMessage());
        }
    }
}
```

## 可选提示

<div class="hint" title="H1：合同与不变量">把正常、边界、异常与失败后状态分别列出，先判断哪条可见测试在区分它们。</div>
<div class="hint" title="H2：最小反例">先从本页机制解释找到一个两三项输入的反例，避免直接加随机压力掩盖错误。</div>
<div class="hint" title="H3：步骤定位">沿下面标准解的步骤检查第一次状态偏离，再决定改哪一段；答案无需先过题即可查看。</div>

## 标准解与逐步解释

[完整实现副本](solutions/OrderParser.java.txt)。以下是同一源码的完整内容；common、辅助类、调用端和全部测试均公开。

```java
package labs.foundation;

import java.util.*;

public final class OrderParser {
    private OrderParser() {}

    public static Order parse(String text, int line) {
        // 作答开始
        Objects.requireNonNull(text, "输入行不能为空");
        if (line < 1) throw new IllegalArgumentException("行号从1开始");
        if (text.length() > 512) throw new ParseFailure(line, "整行", "超过512字符");
        String[] parts = text.split("[|]", -1);
        if (parts.length != 4) throw new ParseFailure(line, "整行", "必须有4个字段");
        for (int i = 0; i < parts.length; i++) parts[i] = parts[i].strip();
        if (parts[0].isEmpty()) throw new ParseFailure(line, "id", "不能为空");
        if (parts[1].isEmpty()) throw new ParseFailure(line, "customer", "不能为空");
        long cents;
        try {
            cents = Long.parseLong(parts[2]);
        } catch (NumberFormatException e) {
            throw new ParseFailure(line, "cents", "必须是long范围内整数");
        }
        if (cents < 0) throw new ParseFailure(line, "cents", "不能为负");
        Order.Status status;
        try {
            status = Order.Status.valueOf(parts[3]);
        } catch (IllegalArgumentException e) {
            throw new ParseFailure(line, "status", "只允许PAID或PENDING");
        }
        return new Order(parts[0], parts[1], cents, status);
        // 作答结束
    }

    public static List<Order> parseBatch(List<String> lines) {
        // 作答开始
        Objects.requireNonNull(lines);
        if (lines.size() > 10000) throw new IllegalArgumentException("批次最多10000行");
        List<Order> result = new ArrayList<>();
        Set<String> seen = new HashSet<>();
        for (int i = 0; i < lines.size(); i++) {
            Order order = parse(lines.get(i), i + 1);
            if (!seen.add(order.id())) throw new ParseFailure(i + 1, "id", "重复订单ID");
            result.add(order);
        }
        return List.copyOf(result);
        // 作答结束
    }
}
```

1. split保留尾空字段，A|甲|1|必须定位status为空，不能先把尾空丢掉变成含混字段数错误。
2. 字段结构、数值转换、业务非负、枚举合法分别判断。只捕获预期转换异常并转成带上下文的ParseFailure；没有catch(Exception)后返回null。
3. parseBatch先逐行建立局部结果，用seen区分重复；失败不返回部分成功批次。扫描O(总字符数+N)，hash期望O(1)不保证恶意碰撞下最坏常数。
4. 后续课使用common/OrderCodec这一完整checkpoint，合同与本题一致，避免上一题尚未填写导致下一题无法运行。它公开可读，不是隐藏实现或评分捷径。

## 源码与证据

[OpenJDK21固定源文件](https://github.com/openjdk/jdk/blob/890adb6410dab4606a4f26a942aed02fb2f55387/src/java.base/share/classes/java/lang/Long.java)，tag jdk-21+35，commit 890adb6410dab4606a4f26a942aed02fb2f55387。符号：Long.parseLong(String)、String.split。

比较数值格式错、溢出与业务负值；库异常与领域校验不能混为同一种失败。

R记录必须含版本/SHA、文件/符号、输入、关键状态、分支、反例与结论。当前补丁JDK的src.zip不是GA原件，动态证据必须分别标识，不能编造断点截图。[源码路线与证据模板](../../../docs/源码与评阅.md)说明如何核对。教学容器只实现已列子集，不称生产级框架。

## 面试问答与迁移

问：解析错误为什么用unchecked异常？答：本API把违反输入合同作为调用失败；文件访问IOException仍是独立层。checked/unchecked是API设计取舍，不是谁更高级。
问：重复ID可不可以last-wins？答：可以作为另一个合同，但本题明确拒绝；CLI综合题将显式采用first-wins并解释差异。
问：异常信息只写“格式错”够吗？答：接入排障需要行、字段、原因，敏感原文则不应无脑全量记录。
迁移：新增可选备注字段，仍保留行号，写空备注/多字段/坏金额测试。

## 完成标准

关键A全部通过；解释、证据、迁移按[评阅标准](../../../docs/源码与评阅.md)至少达到能讲机制和边界。记录H0独立到H4完整答案、首次失败、修复原因，并在24小时后不看答案完成变式。不能用“看懂了/复制后全绿”代替独立掌握，也不承诺面试结果。
