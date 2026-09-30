# C06-03 公开标准答案

## 完整实现

```java
package labs;

import java.sql.*;
import java.time.Instant;
import java.util.*;

/** 游标包含完整排序键；这里只承诺同一稳定数据集内分页，不承诺跨请求全局快照。 */
public final class QueryLab {
    public record Cursor(Instant createdAt, long id) {
        public Cursor {
            Objects.requireNonNull(createdAt);
        }
    }

    private QueryLab() {}

    public static void validateLimit(int limit) {
        if (limit < 1 || limit > 100) throw new IllegalArgumentException("每页必须为 1 到 100 条");
    }

    public static List<Long> after(Connection c, long tenant, Cursor cursor, int limit)
            throws SQLException {
        validateLimit(limit);
        // BEGIN_STUDENT
        return Db.ids(
                c,
                "SELECT id FROM c06_orders WHERE tenant_id=? AND (created_at>? OR (created_at=? AND"
                        + " id>?)) ORDER BY created_at,id LIMIT ?",
                tenant,
                cursor.createdAt(),
                cursor.createdAt(),
                cursor.id(),
                limit);
        // END_STUDENT
    }

    public static List<Long> onUtcDay(Connection c, long tenant, Instant start)
            throws SQLException {
        if (start == null || !start.equals(start.truncatedTo(java.time.temporal.ChronoUnit.DAYS))) {
            throw new IllegalArgumentException("开始时刻必须是 UTC 零点");
        }
        return Db.ids(
                c,
                "SELECT id FROM c06_orders WHERE tenant_id=? AND created_at>=? AND created_at<?"
                        + " ORDER BY created_at,id",
                tenant,
                start,
                start.plusSeconds(86400));
    }

    public static List<Long> slowDay(Connection c, long tenant, String day) throws SQLException {
        return Db.ids(
                c,
                "SELECT id FROM c06_orders WHERE tenant_id=? AND DATE(created_at)=? ORDER BY"
                        + " created_at,id",
                tenant,
                day);
    }

    public static String plan(Connection c, String sql, Object... args) throws SQLException {
        return Db.text(c, "EXPLAIN ANALYZE " + sql, args);
    }
}
```

## 逐步解析

标准解用两项比较展开完整排序，不使用只比较时间的简化。limit仍参数绑定并限制在1..100。日期优化只接受已经定义好的UTC日；86400秒不适用于直接表示任意时区的夏令时自然日。QueryLab.plan 只供受控 SELECT 实验，调用者不得把不可恢复的写语句放进去。复杂度需按索引访问与返回行数描述，不能说所有游标分页都是常数时间。

1. 先确认输入边界与调用者所有的连接，不能在查询辅助方法中提前关闭调用者连接
2. 所有动态值绑定到PreparedStatement；表名/语句结构为课程常量
3. 事务成功才commit，SQL或运行期异常走rollback，后续状态恢复不能悄悄改变业务结果
4. 对照本题全部ContractTest和DatabaseTest，正常结果、边界和故障都要解释
5. 源码阅读、计划、锁诊断和恢复范围属于观察验收，不用固定耗时或私有字段伪装稳定API
6. 替代方案与迁移练习见task.md，任何实现只要满足契约都可接受；不能删除测试放宽契约

## 复杂度、失败边界与替代方案

深 OFFSET 通常仍需要访问并丢弃前面的匹配行，游标能用排序键界定下一页。created_at 不唯一时，游标必须包含 id，条件为 time>t OR (time=t AND id>id0)。半开时间区间避免结束点重复，允许使用普通时间列索引；函数索引是另一种明确设计，不应断言任何函数必定不能用索引。跨页期间有插入、删除、修改时，不承诺全局一致快照，应定义业务语义。

新增批量加载订单明细接口，保证最多两次查询且保留空明细订单；给出统计查询次数的测试和重复行处理。

## 调用方

```java
package labs;

/** 调用前用 Schema.main 显式重置合成数据；密码从环境读取。 */
public final class Usage {
    public static void main(String[] args) throws Exception {
        try (java.sql.Connection c = Db.local()) {
            System.out.println(
                    "第一页之后="
                            + QueryLab.after(
                                    c,
                                    7,
                                    new QueryLab.Cursor(
                                            java.time.Instant.parse("2025-01-01T00:00:00Z"), 1),
                                    10));
        }
    }
}
```

## 检查命令

从课程根执行 ./gradlew :mysql-03-query-03-pagination:test。真实MySQL未运行时不能把纯逻辑绿灯称为完整通过。
