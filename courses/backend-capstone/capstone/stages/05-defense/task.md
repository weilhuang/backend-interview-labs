# 05 盲测变体、库存审计与2/5/15分钟答辩

## 本节要交付什么

这一阶段把“测试绿了”改成“能说明为什么成立，哪里尚未证明”。实现Audit.inspect：每个商品可售库存加所有RESERVED数量必须等于初始库存；取消订单不占用；不存在的商品、负库存、无来源投影、同版本冲突或超前投影都是ERROR；缺少或旧版本投影是LAG。累计数量使用long，报告只读。

生产页面从MySQL同一REPEATABLE READ事务读取审计快照，避免把不同提交时刻的库存和订单拼成假错误。健康状态和积压数是另一次观察，不构成跨服务原子快照。课堂共享一个MySQL实例但订单与配送用不同事务和进程，没有共享RPC事务。

先独立完成审计，再运行scripts/draw-defense.py抽取一个故障、一个新需求、一个设计问题。可见答案一直开放；“盲测”指你在作答前主动不看答案，不代表隐藏测试或强制解锁。把新变体回归写进本节test，产出事故记录与口述稿，不只复述标准答案。

## 先运行完整调用方

先制造读模型落后，审计只能报LAG；完成重放后变为空。再在独占测试容器中故意减一件库存，审计必须报ERROR。用固定种子生成100组预留/取消组合做性质检查。最后抽题，把“客户端超时后换新请求号”作为反例解释双扣风险。

从课程根运行 `./gradlew :05-defense:test :05-defense:usage`。实际数据库与网络验收用 `./gradlew :05-defense:integrationTest`，需要Docker。完整网页调用用 `CAPSTONE_STAGE=05-defense scripts/course.sh start`。所有测试和调用方都可见；不需要先抄完其他阶段的学习区。

```text
数据事实 -> 同一快照 -> 不变量审计 -> 证据表 -> 面试陈述
                      | LAG：可重放      | ERROR：停止猜测
                      +------定点验证----+
2分钟：问题/不变量/结果
5分钟：加事务与确认窗口
15分钟：加源码、故障证据、替代方案、未验证边界
```

## 完整项目在哪里

本节只替换 `src/labs/capstone/Audit.java`。公共应用在 `app/src/main/java/labs/capstone/`，中文页面在 `app/src/main/resources/static/index.html`，其他已完成依赖在公开 `reference/src/labs/capstone/`。Gradle显式排除本节对应的reference同名类，防止测试绕过你的实现。`test/`与`integration-test/`是本节测试；`shared/`是可见的公共测试支撑。根README给出完整结构、接口与启动依赖。

## 逐步动手

1. 在纸上写出本节的失败分支，先预测每次调用是否允许推进状态
2. 运行现有测试，逐个实现学习区；为一个边界补充可见测试
3. 用Usage或页面实际调用，再运行真实集成；记录编译、快测、容器、浏览器各自结果
4. 不看下方答案，解释一个错误实现为什么会被你的新测试拒绝

## 递进提示

1. 先按商品累计仍占用的数量，再检验库存守恒，不要把CANCELLED也加进去。
2. 比较订单版本与投影版本：缺失/落后是LAG，超前/同版本异态是ERROR。
3. 用long累计，并测试投影没有来源订单；输出不可变集合，审计不应自行修复数据。

## 核心源码与断点证据

阅读[OpenJDK21 HashMap.merge](https://github.com/openjdk/jdk/blob/jdk-21%2B35/src/java.base/share/classes/java/util/HashMap.java)与[MySQL8.4一致性非锁定读](https://dev.mysql.com/doc/refman/8.4/en/innodb-consistent-read.html)。本课使用HashMap做O(n+m)审计，不宣称它提供数据库一致性。对照Database.snapshot中的同一Connection与事务，在另一个连接提交订单，记录事务中多次普通SELECT看到的版本；再说明为什么跨库一致快照需要另外的设计。

## 面试递进

**机制：审计发现不守恒能直接把库存补回吗？**

不能，可能存在漏记、重复扣减、错误快照或未建模业务。先保留证据定位原因，自动补数会掩盖问题。

**边界：所有公开用例通过就能宣布生产可靠么？**

不能。只覆盖给定版本、拓扑、负载和故障点；要报告真实运行过的项目和没有验证的边界。

**取舍：为何共享一个MySQL实例？**

降低学习环境资源成本，仍保持本地事务与RPC确认的分离；独立库故障域和容量隔离要另外部署验证。

**追问：如何诚实讲项目经验？**

说“我在隔离实验用这些版本复现了这些故障，并用这些断言验证”，不要改写成生产用户数或从未经历的事故。

## 标准答案与解释（直接可读）

下面是完整作者实现，不依赖折叠渲染或解锁。先对照关键分支，再重新独立实现；公开答案不会被导出排除。

```java
package labs.capstone;

import static labs.capstone.Model.*;

import java.util.*;

/** C14-05：审计只报告事实，不静默修改库存；读模型落后与库存破坏必须区别对待。 */
public final class Audit {
    private Audit() {}

    public record Finding(String severity, String subject, String detail) {}

    public static List<Finding> inspect(
            List<Stock> stocks, List<Order> orders, List<Delivery> deliveries) {
        // 学习区开始
        List<Finding> findings = new ArrayList<>();
        Map<String, Long> reserved = new HashMap<>();
        for (Order order : orders) {
            if (order.quantity() < 1
                    || (!order.status().equals("RESERVED") && !order.status().equals("CANCELLED")))
                findings.add(new Finding("ERROR", order.requestId(), "非法订单状态或数量"));
            if (order.status().equals("RESERVED"))
                reserved.merge(order.sku(), (long) order.quantity(), Long::sum);
        }
        Set<String> known = new HashSet<>();
        for (Stock stock : stocks) {
            known.add(stock.sku());
            long held = reserved.getOrDefault(stock.sku(), 0L);
            if (stock.available() < 0 || (long) stock.available() + held != stock.initial())
                findings.add(new Finding("ERROR", stock.sku(), "可售库存与已保留数量不守恒"));
        }
        for (String sku : reserved.keySet())
            if (!known.contains(sku)) findings.add(new Finding("ERROR", sku, "订单引用不存在的库存"));
        Map<String, Delivery> byRequest = new HashMap<>();
        for (Delivery delivery : deliveries) byRequest.put(delivery.requestId(), delivery);
        Set<String> orderIds = new HashSet<>();
        for (Order order : orders) {
            orderIds.add(order.requestId());
            Delivery projection = byRequest.get(order.requestId());
            if (projection == null || projection.version() < order.version())
                findings.add(new Finding("LAG", order.requestId(), "读模型待重放追平"));
            else if (projection.version() != order.version()
                    || !projection.status().equals(order.status()))
                findings.add(new Finding("ERROR", order.requestId(), "读模型超前或同版本状态冲突"));
        }
        for (Delivery delivery : deliveries)
            if (!orderIds.contains(delivery.requestId()))
                findings.add(new Finding("ERROR", delivery.requestId(), "读模型没有来源订单"));
        return List.copyOf(findings);
        // 学习区结束
    }
}
```

为什么这样实现：前面定义的业务状态、失败边界与源码分支必须对应到代码；每次确认都只能声明它前面的效果已经完成。测试既检查返回值，也检查持久化事实和不会发生的副作用。模仿代码排版不是目标，能用不同写法维持相同合同才算通过。
