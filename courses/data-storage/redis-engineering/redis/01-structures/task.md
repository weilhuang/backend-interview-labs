# C07-01 数据结构与原子命令

## 企业场景与进入条件

订单平台有四种缓存需求：按会话读用户字段、活动排行榜、处理订单去重、短窗口访问计数。假设数据能从事实库恢复，排行榜允许异步刷新；支付事实不以Redis为唯一凭据。先会Java集合、异常、try-with-resources，并能从C06读取一行SQL。目标是以实际命令结果证明选型，而不是背五种数据类型。

本节A验证真实Redis命令和错误分支；O解释pipeline边界；R阅读固定服务端源码。没有Docker只能跑参数校验，不能声称学完服务端原子性。

## 概念、例子与ASCII

String适合序列化快照/整数计数；Hash适合一个实体少量字段；Set天然成员去重；ZSet按分数排序，分数相等时还有成员字典序规则；Stream有条目ID、保留与消费者组语义，但本节只验证追加，不能代替完整可靠消息课程。内部编码会随大小、值和配置改变，逻辑结构与listpack/hashtable等物理编码不是一一固定映射。

```text
会话字段 ------> Hash session:{用户}
订单重复 ------> Set seen:{活动}
排行榜 --------> ZSet rank:{活动} -- score --> 顺序
审计追加 ------> Stream events:{活动}
访问计数 ------> String count:{用户} + TTL

普通两条命令： INCR -> 客户端崩溃 -> PEXPIRE未发出 -> 永久键
Lua一段脚本：  INCR -> 首次时PEXPIRE -> 返回本窗口次数
```

输入成员order-7、order-7、order-8，SCARD返回2；u7得12分、u8得18分，ZREVRANGE首位为u8。计数首次返回1并设置30秒TTL，第二次即使调用者传90秒仍返回2且不延长原窗口。这是固定窗口契约，不是滑动窗口限流。

Pipeline把多个请求集中发出以降低网络往返，并不自动隔离其他客户端，也不回滚错误命令前后的写入。Lua在一次执行期间不与其他常规命令交错，但运行时错误也不回滚已写部分；脚本必须短小、先校验后修改。原子执行不等于数据库事务的全部ACID。

## 编码步骤与调用验证

1. 在本课根运行`./gradlew :redis:01-structures:run`。调用入口是`src/labs/StructuresUsage.java`，应看到用户u7、窗口次数1、去重数2和u8优先的排名。所有键带随机c07前缀，退出删除本次容器
2. 先读`test/labs/StructuresTest.java`，运行`./gradlew :redis:01-structures:unitTest`。零/负TTL必须在连接Redis前拒绝，别让无效输入意外产生永久键
3. 编辑`src/labs/Structures.java`的`incrementWithTtl`。只补Academy高亮实现区：检查TTL、以KEYS传键、ARGV传参数，调用INCR，返回1时设置PEXPIRE，返回计数。不要把不可信键拼进Lua正文
4. 运行`./gradlew :redis:01-structures:test`。此任务包含全部真实集成，缺Docker明确失败。命令结果、首次TTL、第二次不续期是三条独立断言
5. 打开`StructuresIntegrationTest`两个反例。pipeline内先SET、再对String执行HSET、再SET：中间Response.get抛错，但前后SET都成功。Lua先SET再错误HSET：SET结果仍存在。给每条断言画出其能排除的误解
6. 自己增加一个已有非整数String的计数测试，确认INCR报错且不凭空改值。别删除失败断言来“通过检查”

## 标准解逐步解释与边界

[完整公开标准解](solution.md)与Java源码一致。先校验TTL限制1毫秒至24小时，是为了在任何INCR之前拒绝非法或溢出窗口；若先INCR再让PEXPIRE因超大数值报错，Lua也不会撤销计数。一次eval避免INCR后应用退出留下无期限键；仅n==1过期避免每次请求把窗口推迟。这里接受计数上限由Redis有符号整数限制，整数溢出是错误；本题没有自动修复历史遗留“有计数无TTL”键，迁移时需要另外的清理策略。

单次String计数为O(1)，脚本工作量固定。SADD平均O(1)，ZADD通常O(log N)，取前K项还承担返回K项成本。不要从一次小数据调用推断大型排行榜吞吐。Hash字段变更只修改相关字段，但字段级业务约束仍需一致性策略。

替代方案可用MULTI/EXEC把已知命令排队执行；若业务依赖上一步结果，需要WATCH重试或Lua。事务中运行时错误同样不是自动回滚全部命令。Redis Cluster多键Lua需要同一hash slot，本课脚本单键自然满足；后续版本水位题会用同一hash tag。

## 真实源码阅读路线

固定Redis **7.4.7**，不从其他大版本截图抄结论：

- [src/t_string.c](https://github.com/redis/redis/blob/7.4.7/src/t_string.c)：`incrDecrCommand`检查当前值能否解释成整数、是否溢出，再更新；`setGenericCommand`处理NX/XX和TTL
- [src/eval.c](https://github.com/redis/redis/blob/7.4.7/src/eval.c)：`evalGenericCommand`准备脚本执行环境及KEYS/ARGV。向下追踪脚本执行与错误响应，而非把“Lua”两个字当原子性的解释
- [官方pipeline说明](https://redis.io/docs/latest/develop/using-commands/pipelining/)是RTT优化的API背景，页面可能更新；服务端实现仍以固定tag为准

记录入口、分支条件、受影响状态和对应测试。源码网页已校对路径，尚未提供作者服务端断点现场，学习者的R证据需另外保存。

## 面试问题、答案与递进追问

1. **为什么去重不先GET再SET？** 两客户端可同时读空。Set成员或SET NX把判断和更新交给服务端；追问业务效果去重时，Redis键过期/丢失会失去历史，支付仍需数据库唯一约束
2. **pipeline是事务吗？** 不是。它优化往返，命令可局部失败并继续；请用本测试中WRONGTYPE后的SET举证。追问执行顺序与原子性是不同维度
3. **Lua报错之前的写会怎样？** 保留。脚本互斥执行不带撤销日志；把可能报错的类型/输入验证放在写之前，复杂外部副作用不能放进脚本
4. **Hash一定比JSON String省内存吗？** 不一定，字段数、字段长度、编码阈值、访问模式决定；测MEMORY USAGE和编码，不只算字符串字符数
5. **Stream可以保证订单只扣一次吗？** 不能单独保证。消费重投、确认失败和数据库副作用必须幂等；本节只完成追加契约，消费者语义在消息课展开

## 独立迁移与退出评阅

新增“每个商户每分钟最多一次重复提醒”的接口，明确窗口起点、重复请求返回值和缓存丢失后容忍什么。先不看答案写Lua、非法输入、并发和TTL测试；再换成每次访问续期，指出改变的是哪条业务契约。A要求全部断言；O要求讲清pipeline/Lua/事务区别；R要求固定源码文件、符号、关键分支和反例。只粘贴答案、只见绿灯或只背数据类型不能毕业。
