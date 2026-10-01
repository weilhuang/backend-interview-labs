# 固定源码阅读与官方资料

## 阅读证据规范

每次记录：版本/tag或commit、文件与符号、进入条件、关键状态变化、失败分支、对应本课测试、不能推出什么。下面是经过官方raw文件路径与符号校对的阅读入口，不声称作者已运行服务端调试器。网页说明可能更新，固定tag源码与实验镜像版本才是本课边界。

## Redis7.4.7核心链路

| 单元 | 固定源码文件与符号 | 阅读问题 |
|---|---|---|
| 01 | [t_string.c](https://github.com/redis/redis/blob/7.4.7/src/t_string.c) `incrDecrCommand`、`setGenericCommand`；[eval.c](https://github.com/redis/redis/blob/7.4.7/src/eval.c) `evalGenericCommand` | 类型/溢出、NX/TTL、Lua参数与错误响应；原子执行不是撤销已写状态 |
| 02 | [expire.c](https://github.com/redis/redis/blob/7.4.7/src/expire.c) `activeExpireCycle`；[db.c](https://github.com/redis/redis/blob/7.4.7/src/db.c) `expireIfNeeded`；[evict.c](https://github.com/redis/redis/blob/7.4.7/src/evict.c) `performEvictions` | 主动时间预算、访问过期、策略与没有可淘汰键时的返回 |
| 03 | 同版本t_string.c、db.c；应用单飞为T | Redis只存结果与期限，Java单飞不冒充服务端内建功能 |
| 04 | 同版本eval.c、t_string.c；MySQL事务与本Java Store | Lua只覆盖Redis两键，MySQL和Redis没有一个共享原子提交点 |
| 05 | [rdb.c](https://github.com/redis/redis/blob/7.4.7/src/rdb.c) `rdbSaveBackground`；[aof.c](https://github.com/redis/redis/blob/7.4.7/src/aof.c) `flushAppendOnlyFile`；[replication.c](https://github.com/redis/redis/blob/7.4.7/src/replication.c) `waitCommand`、`replicationCountAcksByOffset`、`replicaofCommand` | 保存/刷盘/复制确认的不同边界；role转换不自动隔离旧主 |
| 06 | 同版本t_string.c `setGenericCommand`、eval.c `evalGenericCommand` | token比较属于锁所有权，持久fence由MySQL资源端承担 |
| 07 | Jedis5.2.0真实连接路径与JDK21线程池，见下 | 客户端超时、借还、阻塞与拒绝不同边界 |

2026-09-30云端通过官方raw.githubusercontent.com固定tag下载上述8个文件到未提交的build/source-evidence校对符号；没有修改或发布上游Redis源码。Redis源码有自己的许可，见THIRD_PARTY_NOTICES。

## 客户端和JDK

- [Jedis5.2.0 Connection.java](https://github.com/redis/jedis/blob/v5.2.0/src/main/java/redis/clients/jedis/Connection.java)：连接、socket读与broken状态
- [Jedis5.2.0 Pool.java](https://github.com/redis/jedis/blob/v5.2.0/src/main/java/redis/clients/jedis/util/Pool.java)：getResource与底层池
- [OpenJDK21+35 CompletableFuture.java](https://github.com/openjdk/jdk/blob/jdk-21%2B35/src/java.base/share/classes/java/util/concurrent/CompletableFuture.java)：有界get与异常完成；这是阅读基线，不宣称其每行与当前Temurin补丁完全相同
- [OpenJDK21+35 ThreadPoolExecutor.java](https://github.com/openjdk/jdk/blob/jdk-21%2B35/src/java.base/share/classes/java/util/concurrent/ThreadPoolExecutor.java)：execute、addWorker、processWorkerExit与拒绝

## 官方行为资料

[Redis pipeline](https://redis.io/docs/latest/develop/using-commands/pipelining/)、[过期与淘汰](https://redis.io/docs/latest/develop/reference/eviction/)、[WAIT](https://redis.io/docs/latest/commands/wait/)、[持久化](https://redis.io/docs/latest/operate/oss_and_stack/management/persistence/)、[复制](https://redis.io/docs/latest/operate/oss_and_stack/management/replication/)、[分布式锁](https://redis.io/docs/latest/develop/clients/patterns/distributed-locks/)、[MySQL8.4 InnoDB事务模型](https://dev.mysql.com/doc/refman/8.4/en/innodb-transaction-model.html)、[Testcontainers MySQL模块](https://java.testcontainers.org/modules/databases/mysql/)。这些是机制依据，不把“看过文档”作为实际服务运行证据。
