# C06-01 公开标准答案

## 完整实现

```java
package labs;

import java.sql.*;
import java.util.*;

/** 订单查询保留租户边界，金额使用整数分；每个语句和结果集及时关闭。 */
public final class OrderQueries {
    private OrderQueries() {}

    public static long paidTotal(Connection c, long tenant) throws SQLException {
        // BEGIN_STUDENT
        return Db.scalar(
                c,
                "SELECT COALESCE(SUM(total_cents),0) FROM c06_orders WHERE tenant_id=? AND"
                    + " status='PAID'",
                tenant);
        // END_STUDENT
    }

    public static Map<Long, Long> quantities(Connection c, long tenant) throws SQLException {
        String sql =
                "SELECT i.sku,SUM(i.quantity) FROM c06_orders o JOIN c06_item i ON i.order_id=o.id"
                    + " WHERE o.tenant_id=? AND o.status='PAID' GROUP BY i.sku ORDER BY i.sku";
        try (PreparedStatement p = Db.prepare(c, sql, tenant);
                ResultSet r = p.executeQuery()) {
            Map<Long, Long> result = new LinkedHashMap<>();
            while (r.next()) result.put(r.getLong(1), r.getLong(2));
            return Collections.unmodifiableMap(result);
        }
    }

    public static long cents(String amount) {
        return new java.math.BigDecimal(amount).movePointRight(2).longValueExact();
    }
}
```

## 逐步解析

paidTotal 的 tenant 参数通过 PreparedStatement 绑定，字符串拼接不会出现在查询条件中。COALESCE 把空集合 SUM 的 NULL 转为0。quantities 从支付订单 JOIN 明细，在 SKU 粒度聚合，返回只读 Map。对连接不擅自 close，因为连接属于调用者；PreparedStatement/ResultSet 归方法所有并自动关闭。查询成本取决于行数与索引，不宣称固定 O(1)。

1. 先确认输入边界与调用者所有的连接，不能在查询辅助方法中提前关闭调用者连接
2. 所有动态值绑定到PreparedStatement；表名/语句结构为课程常量
3. 事务成功才commit，SQL或运行期异常走rollback，后续状态恢复不能悄悄改变业务结果
4. 对照本题全部ContractTest和DatabaseTest，正常结果、边界和故障都要解释
5. 源码阅读、计划、锁诊断和恢复范围属于观察验收，不用固定耗时或私有字段伪装稳定API
6. 替代方案与迁移练习见task.md，任何实现只要满足契约都可接受；不能删除测试放宽契约

## 复杂度、失败边界与替代方案

关系模型通过主键标识行，外键约束引用存在，唯一键约束同租户请求号不重复。主外键不能自动防止跨租户关联：本例写入 fixture 固定正确，生产创建接口还须校验客户租户或使用复合外键。JOIN 会扩展行数，因此对订单金额求和要在订单粒度进行，不能在明细 JOIN 后直接 SUM(o.total_cents)。整数分防止二进制浮点误差；cents 用 longValueExact 拒绝小数分和溢出，而不是悄悄四舍五入。

新增退款状态与部分退款明细，定义净收入粒度，写出防重复退款约束和异常回滚测试，不得简单把 PAID 改成 NOT NEW。

## 调用方

```java
package labs;

/** 调用前用 Schema.main 显式重置合成数据；密码从环境读取。 */
public final class Usage {
    public static void main(String[] args) throws Exception {
        try (java.sql.Connection c = Db.local()) {
            System.out.println("已支付总分=" + OrderQueries.paidTotal(c, 7));
            System.out.println("销售数量=" + OrderQueries.quantities(c, 7));
        }
    }
}
```

## 检查命令

从课程根执行 ./gradlew :mysql-01-model-01-order-contract:test。真实MySQL未运行时不能把纯逻辑绿灯称为完整通过。
