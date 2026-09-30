# 01 需求、状态机与业务不变量

## 本节要交付什么

你接到的需求是“一个商品可以被并发下单，取消归还库存，下游最终看到订单状态”。先把它变成可反驳的合同：相同请求号、相同商品和数量返回原结果；同号改参数必须冲突；库存不能为负；取消最多释放一次；收到旧消息不能把取消变回预留。RESERVED只是资源预留，尚无真实付款或出库，因而本阶段的取消可以直接补偿库存。本模型没有自动到期取消；客户端超时只表示结果未知，不会自动归还库存。

容量假设是单机MySQL、20件初始商品、一次1–100件、8个数据库连接。Kafka只有一个教学broker；没有集群容灾或全球唯一身份保证。请求号区分大小写，禁止空白、斜线和控制字符；数据库仍显式使用utf8mb4_0900_bin，不能靠输入规则代替存储规则。

完成validate、sameRequest、mayCancel三个学习区，保留其余完整调用代码。先写合法边界，再写换参数和重复取消。不要把参数检查只放到前端，也不要以重新创建订单的方式处理重试。

## 先运行完整调用方

创建 Command("req-01","book",2)，通过验证；构造已取消订单，再用相同参数调用sameRequest，必须得到原CANCELLED对象。用数量3重试必须抛Conflict。运行本节Usage，观察事件号req-01:1与订单版本对应。

从课程根运行 `./gradlew :01-contract:test :01-contract:usage`。本节只验证领域合同，没有独立容器用例；不要把本节integrationTest零测试当作联调。真实MySQL从02-reliability开始，Kafka与gRPC持久化从03-delivery开始。完整网页调用用 `CAPSTONE_STAGE=01-contract scripts/course.sh start`。所有测试和调用方都可见；不需要先抄完其他阶段的学习区。

```text
未出现 --下单事务--> RESERVED(v1) --取消事务--> CANCELLED(v2)
                   | 原号原参数重试            | 重复取消
                   +----原结果----------------+----不再释放
同号换参数 --> 409；未知响应 --> 原号查询/重试；不能改用新号
```

## 完整项目在哪里

本节只替换 `src/labs/capstone/OrderRules.java`。公共应用在 `app/src/main/java/labs/capstone/`，中文页面在 `app/src/main/resources/static/index.html`，其他已完成依赖在公开 `reference/src/labs/capstone/`。Gradle显式排除本节对应的reference同名类，防止测试绕过你的实现。`test/`与`integration-test/`是本节测试；`shared/`是可见的公共测试支撑。根README给出完整结构、接口与启动依赖。

## 逐步动手

1. 在纸上写出本节的失败分支，先预测每次调用是否允许推进状态
2. 运行现有测试，逐个实现学习区；为一个边界补充可见测试
3. 用Usage或页面实际调用，再运行真实集成；记录编译、快测、容器、浏览器各自结果
4. 不看下方答案，解释一个错误实现为什么会被你的新测试拒绝

## 递进提示

1. 把“合法请求”“重复意图”“取消状态迁移”拆成三种判断，异常含义也应分开。
2. 数量下界1和上界100都包含；请求号保留大小写，不做trim或toLowerCase。
3. 已有订单是最终判断依据。取消后重复下单不能把状态重置为RESERVED。

## 核心源码与断点证据

从[OpenJDK21的Objects.requireNonNull](https://github.com/openjdk/jdk/blob/jdk-21%2B35/src/java.base/share/classes/java/util/Objects.java)追踪空引用检查；在OrderRules.validate与sameRequest打断点。分别输入null、数量0、已取消订单和同号不同商品，记录哪一分支拒绝，异常类型为何不同。源码并不会替你定义业务幂等，合同是本课程自己的领域设计。

## 面试递进

**机制：为什么需要请求号，订单自增ID不够吗？**

请求号标识客户端的业务意图。服务端自增ID在响应丢失后无法让客户端知道此前那次是否已提交。

**边界：用同一请求号改变数量怎么办？**

校验已经保存的商品与数量，拒绝参数冲突；不能返回成功却偷偷忽略新参数。

**取舍：库存不足是否也永久保存为幂等结果？**

本实现回滚失败请求，补货后原号可能成功。若业务要求失败也固定，需新增持久失败状态及结果合同，不能只改错误文案。

**追问：超过一天的请求能否删除去重记录？**

先定义客户端重试窗口和事件保留窗口，再设计归档；删除后旧请求可能再次执行。

## 标准答案与解释（直接可读）

下面是完整作者实现，不依赖折叠渲染或解锁。先对照关键分支，再重新独立实现；公开答案不会被导出排除。

```java
package labs.capstone;

import static labs.capstone.Model.*;

import java.util.Objects;

/** C14-01：所有入口共同使用的不变量，禁止只在页面验证。 */
public final class OrderRules {
    private OrderRules() {}

    public static void validate(Command command) {
        // 学习区开始
        Objects.requireNonNull(command, "请求不能为空");
        identifier(command.requestId(), "请求号");
        identifier(command.sku(), "商品号");
        if (command.quantity() < 1 || command.quantity() > 100)
            throw new IllegalArgumentException("数量必须在1到100之间");
        // 学习区结束
    }

    public static void identifier(String value, String label) {
        // 保留大小写；禁用空白和控制字符，避免URL、日志和数据库身份发生歧义。
        if (value == null || !value.matches("[A-Za-z0-9_-]{1,64}"))
            throw new IllegalArgumentException(label + "只允许1到64个字母、数字、下划线或短横线");
    }

    public static Order sameRequest(Order existing, Command command) {
        // 学习区开始
        if (!existing.requestId().equals(command.requestId())
                || !existing.sku().equals(command.sku())
                || existing.quantity() != command.quantity()) throw new Conflict("同一请求号不能换商品或数量");
        return existing;
        // 学习区结束
    }

    public static boolean mayCancel(String status) {
        // 学习区开始
        if (status.equals("RESERVED")) return true;
        if (status.equals("CANCELLED")) return false;
        throw new Conflict("拒绝未知订单状态：" + status);
        // 学习区结束
    }

    public static void validateEvent(Event event) {
        validate(new Command(event.requestId(), event.sku(), event.quantity()));
        if (event.version() < 1
                || !event.eventId().equals(event.requestId() + ":" + event.version()))
            throw new IllegalArgumentException("事件号必须对应请求版本");
        if (!event.status().equals("RESERVED") && !event.status().equals("CANCELLED"))
            throw new IllegalArgumentException("未知事件状态");
        if ((event.status().equals("RESERVED") && event.version() != 1)
                || (event.status().equals("CANCELLED") && event.version() != 2))
            throw new IllegalArgumentException("状态与版本不匹配");
    }
}
```

为什么这样实现：前面定义的业务状态、失败边界与源码分支必须对应到代码；每次确认都只能声明它前面的效果已经完成。测试既检查返回值，也检查持久化事实和不会发生的副作用。模仿代码排版不是目标，能用不同写法维持相同合同才算通过。
