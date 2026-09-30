# 07 Outbox、幂等投影与有界缓存

对应目录 C10-07。Java 21主线，本节可独立选择Gradle模块；依赖版本、完整源码与发布状态见课程首页。所有调用方、测试、数据定义和标准解直接可见。

## 企业场景

库存数据库成功提交后需要通知搜索/页面读模型。直接“先写数据库再发消息”存在丢事件窗口；反过来也可能发布不存在的业务。发布器崩溃重启后会重复投递，读模型还可能把旧版本重新写回缓存。

## 概念逐层建立

- outbox与业务行在同一个MySQL事务写入，因此在数据库持久化假设成立时不会出现已提交业务没有待发布记录
- relay在Kafka确认后才标记published，二者不原子，确认后崩溃会重复；Kafka幂等生产不能消除应用重新send导致的新逻辑消息
- inbox与读模型在同一个消费端数据库事务提交，重复ID相同载荷被忽略，不同载荷必须报警；版本检查防乱序回退
- 消费数据库提交后、Redis失效前仍有窗口。重复消息也要再次执行失效，不能因inbox重复就提前跳过全部处理
- 缓存值有TTL，版本floor防止旧查询晚到回填。floor元数据长期保存，有明确键数量与清理成本；版本限制在2^53-1以内，避免Lua数值精度丢失
- 轮询简单可控，CDC减少扫描/延迟但引入日志保留、位点、schema演进和连接器运维。这里实现轮询，不把它冒充CDC

## ASCII机制图

```text
业务事务：[product revision+1] + [outbox e1] -> COMMIT
                         |
relay锁一条 -> Kafka ACK -> [published=1] COMMIT
                 |崩溃
                 +----重发e1（允许重复）

消费者：[inbox e1] + [read_model版本条件更新] -> COMMIT
                                            |
                                    Redis floor提高+失效
                                            |
                                       提交Kafka位点
```

## 实际操作与逐步编码

1. 实现OutboxStore.change，把业务与事件同提交；库存不足时两者都回滚，相同eventId参数冲突拒绝
2. 实现publishOne，使用FOR UPDATE SKIP LOCKED分配待发记录，发送失败保留记录
3. 实现Projector.apply：inbox与读模型同事务，按revision只前进；运行乱序、重复、不同载荷和提交前失败测试
4. 编写两个Redis Lua脚本：fill拒绝低于floor版本，invalidate提升floor并删除更旧缓存；多个键在Redis Cluster中需同hash tag，当前单节点实验不宣称跨槽可用
5. Docker真实链路注入Kafka ACK后标记前崩溃，再启动新OutboxStore重发，消费到2条而投影只生效1次
6. 用旧版本回填验证floor拒绝；填入新值再等待TTL过期，检查空缓存而非把不存在当库存0
7. 写一致性边界：停止relay、Redis元数据丢失、数据库恢复旧备份分别会破坏哪个前提；不要写“延迟双删保证强一致”

以下命令用于源码仓库/公开源码包；Academy官方ZIP内用Check/Run或Gradle工具窗口执行同名任务。官方导出可能剔除Wrapper脚本/JAR，不能假设导入目录能直接运行./gradlew。独立服务课需同源shared/versions.env快照，缺失时不能视为发行完成。

本节单元检查：`./gradlew :07-outbox-cache:test`；完整调用端：`./gradlew :07-outbox-cache:run`。含数据库/消息服务的单元另执行 `./gradlew :07-outbox-cache:integrationTest`，Docker不可用应明确失败，不能跳过后当作通过。每次修改先跑对应方法测试，再跑全模块回归。

## 正确性合同与保证边界

保证为至少一次发布加幂等本地投影，不是端到端exactly once。成立条件：数据库已提交数据/outbox不丢、Kafka确认语义与副本配置满足要求、消费者持续重试、去重记录保留足够久。单broker测试不证明broker高可用。若缓存从主库读取且每次查询最长Q、缓存TTL为T，失效永久故障时旧值滞留可按Q+T估算；若从异步读模型填充，还要加已知投影延迟上界L，没有L就不能承诺有限陈旧度。

## 固定版本源码阅读

- [apache/kafka 3.9.1：Sender.java](https://github.com/apache/kafka/blob/f745dfdcee2b9851204ddbbcd423626ab87294bc/clients/src/main/java/org/apache/kafka/clients/producer/internals/Sender.java)
- [apache/kafka 3.9.1：TransactionManager.java](https://github.com/apache/kafka/blob/f745dfdcee2b9851204ddbbcd423626ab87294bc/clients/src/main/java/org/apache/kafka/clients/producer/internals/TransactionManager.java)
- [redis/redis 7.4.7：db.c](https://github.com/redis/redis/blob/4d1a341aaf0b96f9d2c43418efac732e31dc28ad/src/db.c)
- [redis/redis 7.4.7：eval.c](https://github.com/redis/redis/blob/4d1a341aaf0b96f9d2c43418efac732e31dc28ad/src/eval.c)
- [redis/jedis v5.2.0：Jedis.java](https://github.com/redis/jedis/blob/54426424a21070bba3b12454e48aa692efc3a9fa/src/main/java/redis/clients/jedis/Jedis.java)

阅读任务：先在本节测试找到症状，再记录入口、关键状态、分支条件和返回/清理路径。每个结论附输入、版本、符号与反例。详细入口、关键状态、分支条件和实验证据对照见课程 docs/源码路线.md。源码字节哈希与标签解析结果在课程作者验证记录中公开；没有截图不伪称做过IDE断点。

## 公开完整标准解

完整Java文件位于本节 `solutions/`，与本节标准实现逐字同步，依赖接口、调用方和测试也在本节可见。下面列出全部编码区，便于先独立完成再核对；不需要解锁或另取私有分支。

### src/labs/distributed/outbox/OutboxStore.java 的练习实现

```java
          try (var statement =
                  Database.prepare(
                      connection, "SELECT * FROM product WHERE sku=? FOR UPDATE", sku);
              var rows = statement.executeQuery()) {
            if (!rows.next()) throw new IllegalArgumentException("商品不存在");
            int next = Math.addExact(rows.getInt("available"), delta);
            if (next < 0) throw new IllegalArgumentException("库存不足");
            long version = Math.addExact(rows.getLong("revision"), 1);
            Database.update(
                connection,
                "UPDATE product SET available=?, revision=? WHERE sku=?",
                next,
                version,
                sku);
            Database.update(
                connection,
                "UPDATE outbox SET available=?, revision=? WHERE event_id=?",
                next,
                version,
                eventId);
            return new Event(eventId, sku, version, next);
          }
```
### src/labs/distributed/outbox/OutboxStore.java 的练习实现

```java
            try {
              sender.send(event);
            } catch (InterruptedException failure) {
              Thread.currentThread().interrupt();
              throw new SQLException("发布被中断", failure);
            } catch (Exception failure) {
              throw new SQLException("发布未确认，保留outbox等待重试", failure);
            }
            failurePoint.afterSend();
            Database.update(
                connection, "UPDATE outbox SET published=1 WHERE event_id=?", event.id());
            return true;
```
### src/labs/distributed/outbox/Projector.java 的练习实现

```java
          try {
            Database.update(
                connection, "INSERT INTO inbox VALUES (?, ?)", event.id(), event.encode());
          } catch (SQLException failure) {
            if (!Database.duplicate(failure)) throw failure;
            try (var statement =
                    Database.prepare(
                        connection, "SELECT fingerprint FROM inbox WHERE event_id=?", event.id());
                var rows = statement.executeQuery()) {
              rows.next();
              if (!event.encode().equals(rows.getString(1)))
                throw new IllegalArgumentException("相同事件ID的载荷冲突");
            }
            return false;
          }
          try {
            Database.update(connection, "INSERT INTO read_model VALUES (?, 0, 0)", event.sku());
          } catch (SQLException failure) {
            if (!Database.duplicate(failure)) throw failure;
          }
          Database.update(
              connection,
              "UPDATE read_model SET revision=?, available=? WHERE sku=? AND revision<?",
              event.version(),
              event.available(),
              event.sku(),
              event.version());
          beforeCommit.run();
          return true;
```
### src/labs/distributed/outbox/VersionedCache.java 的练习实现

```java
    String script =
        "local f=tonumber(redis.call('GET',KEYS[1]) or '0'); local v=tonumber(ARGV[1]); if v<f then"
            + " return 0 end; redis.call('SET',KEYS[1],ARGV[1]);"
            + " redis.call('HSET',KEYS[2],'version',ARGV[1],'payload',ARGV[2]);"
            + " redis.call('PEXPIRE',KEYS[2],ARGV[3]); return 1";
    return ((Number)
                redis.eval(
                    script,
                    List.of("floor:" + snapshot.sku(), "cache:" + snapshot.sku()),
                    List.of(
                        Long.toString(snapshot.version()), snapshot.encode(), Long.toString(ttl))))
            .longValue()
        == 1;
```
### src/labs/distributed/outbox/VersionedCache.java 的练习实现

```java
    String script =
        "local f=tonumber(redis.call('GET',KEYS[1]) or '0'); local v=tonumber(ARGV[1]); "
            + "if v>f then redis.call('SET',KEYS[1],ARGV[1]) end; "
            + "local c=tonumber(redis.call('HGET',KEYS[2],'version') or '0'); "
            + "if c<v then redis.call('DEL',KEYS[2]) end; return 1";
    redis.eval(
        script,
        List.of("floor:" + event.sku(), "cache:" + event.sku()),
        List.of(Long.toString(event.version())));
```

## 标准解机制、复杂度与替代取舍

change先建立唯一事件键，再锁商品行算单调版本，保存完整投影值。relay一次锁一条并等待有界ACK，适合课堂直观说明失败窗口，吞吐扩展可改短租约批次但需重做崩溃合同。Projector通过条件更新抵抗乱序，不假设Kafka跨分区全序。Lua在单节点原子执行版本检查与写入，floor不随值TTL过期；Redis重建丢floor后暂时只剩TTL边界。

## 面试机制、边界与深入追问

- 问：outbox是否让数据库和Kafka原子提交？答：没有，原子范围只有业务表和outbox；发布仍可能重复，消费者承担幂等
- 问：Kafka幂等生产后为什么还需inbox？答：应用重发、生产者重建、业务侧重复与不同协议边界仍可产生重复逻辑事件
- 问：只删缓存一次有什么竞态？答：旧查询可在删除后把旧结果写回；版本floor或受控TTL改变该窗口，但故障假设必须明确
- 问：最终一致有多久？答：仅“最终”不提供时间上界；需要事件积压、投影处理、查询时长与TTL的可测上限
- 问：轮询和CDC怎么选？答：按吞吐、延迟、数据库扫描成本和运维能力权衡；CDC仍需要位点恢复和幂等消费
- 迁移：增加按sku分区的多个发布器，乱序交付旧事件，验证版本不回退；再设计outbox/inbox清理与重放保留期

## 三阶提示与独立验收

1. 基础提示：先列正常、边界、失败后的持久状态，找到测试的业务断言，不先复制实现
2. 机制提示：把每次外部提交、响应、日志落盘、资源归还画成独立事件，检查任意相邻事件间崩溃的后果
3. 深入提示：找真正执行原子操作的数据库/框架分支，确认幂等、锁、时间与持久化前提没有被内存模型替代

独立完成一个迁移题，补失败测试，解释一份错误实现被哪条断言拒绝，再做5分钟机制答辩。看过标准答案只记录“已阅读”，不能记录“独立掌握”。实际执行通过、未执行和已知边界见课程根中文阶段报告。
