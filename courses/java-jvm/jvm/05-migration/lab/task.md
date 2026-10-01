# C03-05 · Java8到17的行为保持迁移

## 企业场景与进入条件

跨时区账单从Java8升级时，最危险的不是语法改错，而是营业日边界、金额溢出与数据身份发生变化。用同一订单业务保持行为，再讨论record/sealed与模块边界。预计150分钟。

## 可执行目标与合同

MigrationReport.Order不可变且金额非负，id/时间/status非null。total按调用方指定ZoneId的LocalDate营业日累计PAID，区间[startOfDay, nextStartOfDay)，溢出抛ArithmeticException；输入列表/日期/时区非null。日期不是固定86400秒。find返回Optional表达缺失，outcome映射sealed层次，label使用switch表达式，explain使用Java17稳定instanceof pattern。

主线统一JDK21。scripts/lab.py migration另外用同一JDK21的--release8编译LegacyReport、--release17编译本题现代实现并执行同业务样例；这验证目标API编译，不能称为真实8/17虚拟机实测。modules实验包括完整两个模块和未导出包的预期编译错误。

分类：A为公开契约与资源回归；O为运行观察与解释；R为固定真实源码阅读；T为显式缩小的教学模型。测试通过不意味着O/R完成。JDK21为主线，Gradle8.10.2、JUnit5.11.4；无前端、无Docker、无真实业务数据。

## 机制图解

```text
Java8 普通类/循环 -> 相同订单合同 -> Java17 record/Stream
                                |
                                v
                 时间点Instant + 营业时区ZoneId
                                |
                     当地日期边界[开始,次日开始)

orders.app --requires--> orders.core --exports--> orders.api
                                      |
                                      +-- orders.internal 不导出
```

## 编码与验证步骤

**Academy官方归档导入模式**：用本题Check检查作答，打开对应Usage.java的main运行按钮，或用IDE的Gradle工具窗口执行test/run。Academy2026.9官方导出实际会剔除gradlew、gradlew.bat与gradle-wrapper.jar，仅保留properties；不要在缺少Wrapper的导入目录照抄终端./gradlew命令。项目SDK与Gradle JVM均用完整JDK21。

**源码仓库或普通Gradle学员副本模式**：以下./gradlew命令针对含Wrapper的课程根，Windows用gradlew.bat。完整CLI与诊断教程保留；首次依赖解析失败应区分环境问题与作答失败。

1. 在课程根运行python scripts/lab.py doctor，确认完整JDK21。缺环境记INVALID_ENV，不判断知识水平。
2. 打开本题src与test全部文件，先运行调用端、读成功与失败样例。作者源码是完整解；学习者副本占位区才是待实现区域，答案也直接在本页下方。
3. 只修改答案区，保持公开合同。先运行本题测试，再补边界/异常测试；不要改掉断言消灭失败。
4. 课程根运行./gradlew :jvm-05-migration-lab:test 与 :jvm-05-migration-lab:run。Windows使用gradlew.bat。首次联网下载依赖与编码错误分开处理。
5. 观察入口：python scripts/lab.py migration。记录JDK完整版本、命令、输入、预期、实际和边界。新证据输出build/evidence，不覆盖此前结果。

## 完整调用示例

以下调用端文件、src下辅助类、test下所有测试均对学习者可见；没有隐藏评分逻辑。

```java
package labs.jvm;

public final class MigrationReportUsage {
    public static void main(String[] args) {
        var order =
                new MigrationReport.Order(
                        "A",
                        300,
                        java.time.Instant.parse("2024-03-10T05:00:00Z"),
                        MigrationReport.Status.PAID);
        System.out.println(
                "纽约营业日总额="
                        + MigrationReport.total(
                                java.util.List.of(order),
                                java.time.LocalDate.of(2024, 3, 10),
                                java.time.ZoneId.of("America/New_York")));
        System.out.println(
                "缺失结果="
                        + MigrationReport.explain(
                                MigrationReport.outcome(java.util.List.of(order), "B")));
    }
}
```

## 渐进提示（可选，不锁答案）

<div class="hint" title="H1：先明确不变量">把合同拆为正常、边界、异常、清理四类，先找哪个可见测试证明当前机制。</div>
<div class="hint" title="H2：用最小反例">比较本题说明中的易错边界与完整测试；写一个能区分两种实现的最小输入。</div>
<div class="hint" title="H3：对照步骤">按下面标准解的逐步解释检查状态变化，先定位错误层，再决定是否重写。</div>

## 标准解与逐步解释

[可单独打开完整标准解](solutions/MigrationReport.java.txt)。同一实现也在这里完整展示，无须切分支、解锁或先通过题目。

```java
package labs.jvm;

import java.time.*;
import java.util.*;

public final class MigrationReport {
    public enum Status {
        PAID,
        PENDING
    }

    public record Order(String id, long cents, Instant created, Status status) {
        public Order {
            Objects.requireNonNull(id);
            Objects.requireNonNull(created);
            Objects.requireNonNull(status);
            if (cents < 0) throw new IllegalArgumentException("金额不得为负");
        }
    }

    public sealed interface Outcome permits Found, Missing {}

    public record Found(Order order) implements Outcome {}

    public record Missing(String id) implements Outcome {}

    private MigrationReport() {}

    public static long total(List<Order> orders, LocalDate day, ZoneId zone) {
        // 作答开始
        Objects.requireNonNull(orders);
        Objects.requireNonNull(day);
        Objects.requireNonNull(zone);
        var start = day.atStartOfDay(zone).toInstant();
        var end = day.plusDays(1).atStartOfDay(zone).toInstant();
        return orders.stream()
                .filter(o -> o.status() == Status.PAID)
                .filter(o -> !o.created().isBefore(start) && o.created().isBefore(end))
                .mapToLong(Order::cents)
                .reduce(0, Math::addExact);
        // 作答结束
    }

    public static Optional<Order> find(List<Order> orders, String id) {
        Objects.requireNonNull(id);
        return orders.stream().filter(o -> id.equals(o.id())).findFirst();
    }

    public static Outcome outcome(List<Order> orders, String id) {
        return find(orders, id).<Outcome>map(Found::new).orElseGet(() -> new Missing(id));
    }

    public static String label(Status status) {
        return switch (status) {
            case PAID -> "已付款";
            case PENDING -> "待付款";
        };
    }

    public static String explain(Outcome outcome) {
        if (outcome instanceof Found found) return found.order().id();
        return ((Missing) outcome).id() + "未找到";
    }
}
```

1. Order构造统一校验，record的final字段不会让字段引用的任意对象都深不可变。本题使用String、Instant、enum与long，恰好具有合适值语义；换成List字段必须复制。
2. 用LocalDate.atStartOfDay(zone)解析营业日起点，再由下一个当地日期得到终点。春季日可能23小时，秋季日可能25小时。测试覆盖两次01:30对应不同Instant的秋季重复时段。
3. Stream过滤只表达业务选择，reduce使用Math.addExact避免Long.sum静默环绕。lambda不是并行保证，本例不使用parallelStream。
4. Optional用于返回可能缺失的结果；不要用get逃避分支，也不要把所有字段机械包Optional。sealed限制直接子类型，Java17这里用instanceof而非把当时预览的pattern switch当正式特性。
5. var是局部编译期类型推断，不是动态类型；record改变生成的API与equals行为，迁移旧有可变POJO可能破坏框架要求或序列化约定。modules的requires表示可读，exports表示API可访问，opens针对深反射，三者不可互换。
6. 总额算法O(N)、附加空间O(1)（流管线固定开销）；循环版本是完整可接受替代。源兼容、二进制兼容、行为兼容应分别测试；--release不会替你测试目标VM运行或第三方库。

## 源码与证据

固定OpenJDK21 GA tag jdk-21+35，commit 890adb6410dab4606a4f26a942aed02fb2f55387。[真实源文件](https://github.com/openjdk/jdk/blob/890adb6410dab4606a4f26a942aed02fb2f55387/src/java.base/share/classes/java/time/LocalDate.java)；符号：LocalDate.atStartOfDay(ZoneId)、ZoneRules.getTransition。完整出处和补充规范见课程根[源码阅读清单](../../../docs/源码阅读清单.md)。

给纽约夏令切换日与午夜缺口时区（需核对tzdb版本）打断点，区分普通午夜、gap调整和overlap策略。记录时区数据版本与Instant，解释本题比较的半开区间；不要把某个地区规则当永久不变。

R证据至少包含项目/版本/SHA、文件与符号、输入、关键分支、状态值、结论及反例。源码网页定位不等于已实际断点；本课程没有伪造截图。若IDE默认打开供应商补丁版源码，请另记录该版本，不冒充GA调试已完成。

## 面试问答与迁移

- 问：为什么营业日不能用Instant加24小时？答：营业日是当地日历概念，时区规则会跳变；测试纽约2024-03-10给出反例。纯持续时长计费才适合Duration。
- 问：record能替代所有实体吗？答：适合值载体；可变身份实体、代理继承、无参构造框架都有边界。声明record并不自动完成领域建模。
- 问：Stream一定比for更好吗？答：不一定。以清晰、可测合同、复杂度与分配测量选择；有副作用和多步失败回滚时循环可能更直接。
- 问：模块报包不可见应直接--add-exports吗？答：先确认是否用了内部API；修复应依赖已导出API。临时开关属于迁移例外，要记录退出计划；本题正常路径无需开关。
- 迁移：新增“按客户所在地营业日退款”，保证金额和日期规则在8风格与17风格相同；给可变List字段加入防御性复制反例。

## 完成与复盘

A必须真正通过；O/R提交证据并按根目录[评阅标准](../../../docs/评阅标准.md)评阅。记录H0独立/H1-H4提示、首次失败、改动原因、24小时后换条件回测。至少能用一个反例解释结论边界。课程不以关键词计分，也不承诺面试结果。
