# C06-02 公开标准答案

## 完整实现

```java
package labs;

import java.sql.*;
import java.time.Instant;
import java.util.*;

/** EXPLAIN 为观察证据，优化器选择不作为跨机器固定断言。 */
public final class IndexLab {
    private IndexLab() {}

    public static final String QUERY =
            "SELECT id,created_at FROM c06_orders WHERE tenant_id=? AND status=? AND created_at>=?"
                + " ORDER BY created_at,id LIMIT 20";

    public static void addIndex(Connection c) throws SQLException {
        if (Db.scalar(
                        c,
                        "SELECT COUNT(*) FROM information_schema.statistics WHERE"
                            + " table_schema=DATABASE() AND table_name='c06_orders' AND"
                            + " index_name='idx_c06_feed'")
                == 0) {
            // BEGIN_STUDENT
            Db.update(c, "CREATE INDEX idx_c06_feed ON c06_orders(tenant_id,status,created_at,id)");
            // END_STUDENT
        }
    }

    public static void seedDistribution(Connection c, int n) throws SQLException {
        if (n < 1 || n > 100_000) throw new IllegalArgumentException("行数必须在 1 到 100000 之间");
        Db.transaction(
                c,
                tx -> {
                    try (PreparedStatement p =
                            Db.prepare(tx, "INSERT INTO c06_orders VALUES(?,?,?,?,?,?,?)")) {
                        for (int i = 1; i <= n; i++) {
                            p.setLong(1, 1000 + i);
                            p.setLong(2, i % 100 == 0 ? 8 : 7);
                            p.setString(3, "plan-" + i);
                            p.setLong(4, i % 100 == 0 ? 3 : 1);
                            p.setString(5, i % 4 == 0 ? "NEW" : "PAID");
                            p.setLong(6, 100);
                            p.setTimestamp(
                                    7,
                                    Timestamp.from(
                                            Instant.parse("2025-02-01T00:00:00Z").plusSeconds(i)));
                            p.addBatch();
                            if (i % 500 == 0) p.executeBatch();
                        }
                        p.executeBatch();
                    }
                    return null;
                });
        Db.text(c, "ANALYZE TABLE c06_orders");
    }

    public static String explain(Connection c, boolean execute) throws SQLException {
        return Db.text(
                c,
                (execute ? "EXPLAIN ANALYZE " : "EXPLAIN FORMAT=JSON ") + QUERY,
                7,
                "PAID",
                Instant.parse("2025-01-01T00:00:00Z"));
    }

    public static List<Long> result(Connection c) throws SQLException {
        return Db.ids(c, QUERY, 7, "PAID", Instant.parse("2025-01-01T00:00:00Z"));
    }
}
```

## 逐步解析

标准解只在索引不存在时创建，information_schema.statistics 校验列顺序。测试断言索引定义和结果不变，实际计划只验证真实执行信息存在，并完整输出供评阅。受控分布 seedDistribution 使用批量 PreparedStatement 与事务；最多10万行，避免误生成无限数据。性能报告记录版本、分布、缓存冷热和计划，不能把日志当性能基准。

1. 先确认输入边界与调用者所有的连接，不能在查询辅助方法中提前关闭调用者连接
2. 所有动态值绑定到PreparedStatement；表名/语句结构为课程常量
3. 事务成功才commit，SQL或运行期异常走rollback，后续状态恢复不能悄悄改变业务结果
4. 对照本题全部ContractTest和DatabaseTest，正常结果、边界和故障都要解释
5. 源码阅读、计划、锁诊断和恢复范围属于观察验收，不用固定耗时或私有字段伪装稳定API
6. 替代方案与迁移练习见task.md，任何实现只要满足契约都可接受；不能删除测试放宽契约

## 复杂度、失败边界与替代方案

InnoDB 聚簇索引的叶子存储整行；二级索引叶包含主键值，取未覆盖列可能再按主键访问。联合索引遵循字典序，但不能把“最左前缀”简化成任何情况下缺首列必定全表扫；优化器可能选其他路径。筛选、排序、返回列共同决定索引。查询中 tenant/status 等值，created_at 范围，id 是稳定排序补充；索引通常可以承载需要的列，但实际路径由统计信息和代价决定。

增加商家维度和最近7天待付款查询，给出两个索引候选，比较相同负载的读写成本与计划，不用强制索引掩盖错误设计。

## 调用方

```java
package labs;

/** 调用前用 Schema.main 显式重置合成数据；密码从环境读取。 */
public final class Usage {
    public static void main(String[] args) throws Exception {
        try (java.sql.Connection c = Db.local()) {
            System.out.println("索引前=" + IndexLab.explain(c, false));
            IndexLab.addIndex(c);
            System.out.println("索引后=" + IndexLab.explain(c, true));
            System.out.println("结果=" + IndexLab.result(c));
        }
    }
}
```

## 检查命令

从课程根执行 ./gradlew :mysql-02-index-02-plan-evidence:test。真实MySQL未运行时不能把纯逻辑绿灯称为完整通过。
