# C07-02 过期淘汰与容量

## 企业场景与进入条件

商品详情缓存最多允许一个值64KiB，业务希望30秒内失效，Redis内存耗尽时仍能解释请求失败。容量不是把机器内存写进一个数字：序列化、对象开销、连接缓冲、复制/AOF缓冲、后台持久化的写时复制都消耗资源。先完成C07-01，区分字符数和UTF-8字节数。

A覆盖输入限额、TTL契约及真实maxmemory分支；O记录内存、编码、访问形态；R追踪过期与淘汰。没有Docker的纯测试只证明Java入口拦截，不证明Redis容量行为。

## 概念、例子与ASCII

```text
读请求 -> lookup -> 到过期时间? -> 视为不存在（惰性检查）
时间事件 --------> 抽样检查过期键（主动清理，受预算约束）
写入需求 --------> 内存超上限? -> 按策略选择受害键 / 返回OOM

有效期规则            容量规则
TTL截止时间           maxmemory + 淘汰策略
“何时不再可见”        “不足空间时允许丢谁”
```

PTTL返回-2表示不存在，-1表示存在但无期限，非负值是剩余毫秒。后台什么时候真正回收内存不适合断言为精确某一毫秒；业务读已过期键应当按缺失处理。本测试对当前TTL只断言合理范围，再用PEXPIRE 0确定性进入删除状态。

noeviction在不能满足写入内存要求时拒绝相应命令，不能理解为“永不报错”；allkeys-lru允许所有键被淘汰，volatile类策略只从带过期时间的键选择。LRU/LFU是近似选择，不承诺某个精确键下一次一定被移除。带无TTL版本水位的C07-04不能随意放到allkeys淘汰域，否则一致性保护也会丢失。

“中文”是2个Java可见汉字，却是6个UTF-8字节。配置maxBytes=3时本地直接返回false；容量64字节且TTL为30秒时可写入并观测编码与MEMORY USAGE。返回false代表主动拒绝缓存，不代表订单业务失败，应由调用方按规则回源。

## 编码步骤与调用验证

1. 运行`./gradlew :redis:02-expiry:run`，查看中文值、PTTL、MEMORY USAGE、OBJECT ENCODING和主动过期后的null。端口由临时容器映射，不要连接公司Redis
2. 运行`./gradlew :redis:02-expiry:unitTest`。观察“中文”超出3字节的边界。修改`src/labs/Expiry.java`的`put`实现区，拒绝null和非正TTL，并在发命令前按UTF-8字节数限额
3. 用一条SET PX同时设置值和期限，避免SET成功后PEXPIRE未执行的永久缓存窗口。不要用先SET后补TTL的两次往返替代
4. 运行`./gradlew :redis:02-expiry:test`。真实测试创建分别配置noeviction和allkeys-lru的两个独立容器，每个上限4MB，每次128KiB，最多96次。写入有上限，绝不向宿主机无限塞内存
5. noeviction场景必须捕获包含OOM的服务端错误；allkeys-lru场景必须看到evicted_keys增加，但不能断言key17一定被删。记录INFO memory的used_memory、mem_fragmentation_ratio、mem_not_counted_for_evict（目标版本存在时）和配置
6. 加入一个较多字段Hash观察，比较同样业务数据的命令数量和占用，说明采样时间与版本。性能和内存比较只交O报告，不加“必须快两倍”断言

## 标准解逐步解释与边界

[完整公开标准解](solution.md)。构造器验证容量；put验证内容和TTL；UTF-8编码测量后再调用SET PX；observe仅用于观测，不保证多个命令之间快照一致，键可能在PTTL与MEMORY USAGE之间过期。真实测试默认期限足够长，但仍不用等值的毫秒断言。

测量字节需要O(N)编码空间与时间。本实现为简明可能为超大字符串分配临时字节数组；生产入口还应限制HTTP请求体、反序列化大小。Redis maxmemory是独立保护，单值限额不能防止海量小键。两道限制解决不同问题。

热键是访问集中，大键是数据体积/成员数大；两者可同时出现也可独立存在。SCAN适合渐进遍历但不是强一致快照。big key检测应限制扫描预算，读取完整集合会把诊断变成事故；删除大键可评估UNLINK异步释放，但后台资源并非零成本。本课不对真实共享实例执行KEYS或清库。

## 真实源码阅读路线

固定Redis **7.4.7**：

- [src/db.c](https://github.com/redis/redis/blob/7.4.7/src/db.c)的`lookupKeyReadWithFlags`/`expireIfNeeded`，观察访问时的过期判断和主从角色差异
- [src/expire.c](https://github.com/redis/redis/blob/7.4.7/src/expire.c)的`activeExpireCycle`，查抽样、时间预算和再次扫描的条件。说明为什么“到点全量清扫所有键”错误
- [src/evict.c](https://github.com/redis/redis/blob/7.4.7/src/evict.c)的`performEvictions`，查内存状态、策略分支、选择候选以及无法淘汰时的返回结果
- [官方淘汰说明](https://redis.io/docs/latest/develop/reference/eviction/)用于配置含义；以冻结版本实测为最终证据

R记录真实函数入口和一次对应分支，不把教案图当源代码，也不宣称本环境已做服务端单步调试。

## 面试问题、答案与追问

1. **TTL到了键一定从内存消失吗？** 业务可见性与物理释放时刻不同，惰性访问与主动周期配合；追问如何测试时，应验证GET结果和有界最终状态，而非某一毫秒内存下降
2. **allkeys-lru和volatile-lru如何选？** 前者可能删任何业务键，后者限制到有TTL的候选。选择取决于哪些键允许丢；若只剩无TTL键，volatile策略可能无候选而OOM
3. **maxmemory等于进程RSS上限吗？** 不等于。额外缓冲、碎片、fork等都需预算，记录Redis指标与容器进程指标，不能只画一个等号
4. **热键怎么治？** 先看请求分布与业务：本地短缓存、请求合并、复制读、拆分可分解的聚合；每种都有一致性/失效边界。给热键加随机后缀会破坏计数语义
5. **大键删掉服务一定马上恢复吗？** 同步删除可能阻塞，异步释放也消耗CPU/内存；要结合慢日志、延迟和负载证据，不仅看DEL返回值

## 独立迁移与退出评阅

给缓存增加总业务配额，例如每个租户最多1000个活跃订单；写清它与Redis淘汰策略的竞争关系。用确定性输入验证超限后的业务降级，不依赖“哪一个键恰好被LRU删掉”。提交A测试、O容量表和R路径，口述一次冷热分布变化如何改变结论。若纯逻辑通过但容器实验未跑，只记为入口校验通过。
