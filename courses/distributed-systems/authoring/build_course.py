#!/usr/bin/env python3
"""从公开标准实现生成Academy元数据、学生占位与各节完整答案。"""
from pathlib import Path
import json,re,shutil,yaml
R=Path(__file__).resolve().parents[1]
TASKS=[
('01-failure-model','01 故障模型、网络与未知结果','C10-01',
'''电商调用方在200毫秒内未拿到库存响应。客服问“是不是没有扣库存”。同一超时现象既可能对应请求没有到达，也可能对应事务已经提交而响应丢失。先用可控事件模型区分业务事实与调用方知识，再到后两节观察真实网络。''',
'''- 故障模型中的进程崩溃、消息丢失、延迟、重复、乱序分别改变什么，不能用一个“异常”代替
- TCP提供单连接有序字节流，不提供消息边界或业务恰好执行一次；HTTP需要自己的请求/响应与幂等合同
- HTTP/2在一条TCP连接上多路复用流，连接级故障仍会影响多条流；应用流控和TCP拥塞控制不是同一层
- DNS缓存和连接池会延长旧地址的影响。建连、取连接、写、读、总deadline需要分开预算
- CAP中的一致性通常指线性一致性，可用性有严格“非故障节点收到的请求最终有响应”定义。发生分区时，跨分区维持线性一致性可能拒绝/等待请求；不能把CAP说成平时任选两个
- PACELC补充无分区时复制延迟与一致性取舍。这里没有实现共识协议，事件模拟不能证明CAP或任何数据库的全局性质''',
'''调用方                  网络                 服务端
  SEND -------------------------------> 本地事务COMMIT
   |                       X <----------- REPLY丢失
  TIMEOUT
   v
 UNKNOWN（可能提交，也可能没到达）
   |
 同一业务键查询/恢复，而不是把未知改成失败''',
'''1. 运行 `:01-failure-model:run`，写出时间点0、10、20、30毫秒的调用方状态
2. 在 `Lab.simulate` 实现状态转换。运行 `LabTest.提交成功但响应丢失仍是未知` 与延迟响应测试
3. 构造同样的UNKNOWN但提交次数分别为0和1的事件序列，解释为何调用方无法从超时区分
4. 实现 `downstreamBudget`：从剩余100毫秒保留30毫秒，下游上限80毫秒，得到70毫秒；不足时返回0
5. 运行全部测试，再自己加一个重复发送导致二次提交的反例；不要修改合同强行让未知等于失败''',
'''时间为非负逻辑毫秒，同一时刻按输入顺序。晚到响应不复活已经结束的调用。COMMIT计数是故意没有幂等保护的模型。模型没有模拟TCP重传、持久化、跨线程竞态；网络事实由C10-02/03测试。''',
'''模拟器保留知识状态和提交次数两个维度，避免把客户端超时解释成远端回滚。复杂度为排序O(n log n)、轨迹O(n)。预算用Duration的减法和比较，而不把各跳timeout直接相加。另一种正确实现可先检查remaining<=reserve，再返回min(remaining-reserve, cap)。''',
'''- 问：超时为何不能当作失败？答：提交与响应是两个不同事件。追问：如果只有读请求呢？读本身无写副作用，但结果仍可能过期，重试也消耗预算
- 问：有TCP为何还会重复订单？答：应用在另一次调用中重发业务请求；TCP序号只对连接字节有效。边界：断连后重建连接不共享业务去重状态
- 问：连接池越大越好吗？答：过大可把排队移到数据库，增加尾延迟；用到达率、服务时间和下游容量定额度
- 问：CAP与数据库事务ACID中的C一样吗？答：不是，前者讨论副本读写一致性，后者约束事务前后的业务/数据不变量
- 迁移：增加“客户端取消但服务端忽略取消”的事件，证明取消和回滚也不是同义词'''),
('02-grpc','02 gRPC真实网络、截止与流控','C10-02',
'''订单网关调用库存服务，同时服务端向慢消费者推送库存快照。一次调用可能经过两跳，前端总预算不能在每跳重新计算。消费者只处理一条时，服务端不能无限制在应用层积累数据。''',
'''- proto字段编号是线协议契约。增添可选含义字段通常比复用已删除字段安全；保留字段编号，测试未知字段往返
- unary与server-streaming有不同生命周期；gRPC状态码在调用边界表达INVALID_ARGUMENT、FAILED_PRECONDITION、UNAVAILABLE、RESOURCE_EXHAUSTED
- stub上的deadline限制等待；Context携带截止和取消通知，业务自己启动的线程、数据库事务仍需独立关闭/超时
- 拦截器传递经过长度/字符集校验的追踪标识。它不是认证凭据，不能当作租户身份
- HTTP/2流控只控制数据流量，不等于业务请求准入。`isReady`表示框架可继续接受写入，不保证消息已交付消费者
- 本机测试用真实Netty TCP，明确关闭in-process捷径；明文只限127.0.0.1实验。生产需要证书、服务身份与授权''',
'''客户端[总预算4秒]
   | gRPC HTTP/2 + trace-id + deadline
   v
网关 Context[剩余<4秒]
   | 显式下游上限8秒，但有效值=min(上下文剩余,8秒)
   v
库存服务 -> 响应剩余预算、追踪标识

订阅者 request(1) -> 框架流控 -> onNext一次
                  cancel -> 服务端onCancel清理''',
'''1. 读 `proto/inventory.proto` 和完整生成文件。运行 `:02-grpc:run` 确认打印随机TCP端口、库存、追踪和剩余预算
2. 编写 `TraceInterceptor.interceptCall`，用参数合法/非法/缺失测试验证，不用ThreadLocal保存请求身份
3. 编写 `Service.reserve` 参数检查：有效幂等键、数量1到1000；运行真实网络参数测试
4. 在两跳测试中观察下游剩余时间不超过上游；把下游上限设大也不能突破Context截止
5. 触发wait故障分支，在截止后确认activeWaits归零。区分客户端收到错误与服务端清理完成两个断言
6. 实现watch的isReady/onCancel循环，使用手动request(1)证明应用只收到一条，然后取消
7. 增加未知字段99，旧消息读出再写回仍保留未知字段；不要把兼容测试写成字符串比较''',
'''默认没有写操作自动重试，channel.disableRetry。示例Backend只是可替换业务接口，网络单元中的固定库存不是持久化实现；C10-08注入真实MySQL幂等存储。订阅最多128条，消息大小受1MiB入口限制，生成载荷用于观察流控。截止不承诺中止已提交SQL。''',
'''拦截器在业务执行前建立Context；自动跨跳deadline取较短者。取消监听器只释放明确拥有的挂起资源；不要在RPC关闭时回滚另一事务。流控写入在回调中检查isReady，最多生成128条，空间主要由框架有界写缓冲和单消息大小决定。`client`保留deadline与metadata，所有Endpoint关闭channel和server并等待退出。''',
'''- 问：deadline和timeout有什么不同？答：deadline约束整体完成时点，每跳消耗剩余预算；多个独立timeout容易累计超时。边界：跨主机不直接比较System.nanoTime
- 问：DEADLINE_EXCEEDED之后库存一定没变？答：不一定，业务提交和响应存在窗口，写入必须带可查询的幂等键
- 问：onNext返回就是发送完成吗？答：不是，可能仅排入框架缓冲。追问：应用忽略isReady会怎样？可能放大内存和取消后浪费
- 问：为什么追踪标识不是用户身份？答：它由调用方可控，只关联日志；鉴权需要可信签名/令牌及服务端授权
- 问：修改proto字段类型有什么风险？答：编号与wire type/语义都参与兼容；旧端可能静默误读，需保留编号并设计迁移
- 迁移：新增只读批量库存查询，保留总预算和消息上限，测试空列表、超过上限与消费者提前取消'''),
('03-dubbo','03 Dubbo调用链、发现与治理','C10-03',
'''同一库存契约在Java服务间使用Dubbo。两台提供者通过真实ZooKeeper发布地址，消费者轮询分配请求；其中一台退出后，不把注册发现变化误当作调用立即无错误。''',
'''- 注册中心负责提供者地址及变化通知；业务请求由消费者直接通过Dubbo协议到提供者，不经注册中心转发
- `ReferenceConfig`构建代理，cluster/router/loadbalance选择Invoker，协议层完成序列化与远程传输，filter建立横切处理
- 本课显式`setScope("remote")`，防止同一JVM部署误走本地调用，网络结果包含提供者ID和附件
- 本课使用failfast+应用层只读有界重试。写reserve没有自动重试；本节fixture提供计数副作用暴露风险，C10-08通过可注入Inventory实现接入MySQL幂等合同
- provider filter校验trace和remaining budget，消费者每次尝试重新计算同一个总截止的剩余时间，并清理附件
- 真实嵌入式ZooKeeper仅在测试中运行，随机回环端口。生产集群多数派、ACL、会话过期与跨地域部署不是一个TestingServer可证明的能力''',
'''提供者A --注册--> ZooKeeper <--订阅-- 消费者代理
提供者B --注册-->     |                  |
                     +--地址通知------> Directory
                                         |
                        cluster -> loadbalance -> Invoker
                                         |
                        TCP Dubbo -> provider filter -> Inventory''',
'''1. 运行 `:03-dubbo:run`：看到真实Dubbo协议结果，读取接口Inventory和两个完整调用类
2. 实现 `BudgetFilter.invoke`，拒绝非法追踪和0/过大预算；先理解过滤器何时执行，再修改业务方法
3. 实现 `Client.quote` 的单个总预算循环，只对非业务RpcException尝试重试；每次finally清理client attachment
4. 运行DubboTest确认参数拒绝与只写一次，再停止提供者，断言有限时间内结束而非无限等待
5. 运行DiscoveryTest：真实ZooKeeper启动，两提供者注册地址；12次调用应覆盖两个提供者
6. 停止一个提供者，等待注册通知与调用恢复，在有界8秒观察窗口内确认另一个可用。记下短暂失败是发现延迟还是业务异常
7. 源码断点从ReferenceConfig.get走到FailoverClusterInvoker.doInvoke，比较本实验failfast为什么没有隐式多次写入''',
'''只读quote最大3次、总预算最多5秒。每次写reserve只调用一次，未知结果后不盲目重发。注册发现测试的单节点ZooKeeper与本机端口只证明协议集成，不代表生产HA。`budget-ms`是收到时的相对上限，不能宣称天然解决任意时钟/传输延迟；调用方总预算与Dubbo超时共同限制等待。''',
'''provider使用ServiceConfig导出实际网络协议，consumer限定remote scope。外层重试重新计算remaining并传入RPC附件，永久业务错误直接抛出。调用完成后移除附件，避免复用工作线程串联不同请求。发现和故障测试使用真实注册服务，但其恢复时长不用于任何生产SLO承诺。''',
'''- 问：注册中心宕机后业务一定不可用？答：已有地址缓存可继续调用仍健康提供者，新发现/变更传播受影响；必须区分控制面与数据面
- 问：retries=2代表几次尝试？答：通常是初次加两次重试，必须按固定源码确认；多层3次可放大成3的层数次
- 问：为什么写请求禁用框架重试？答：没有持久化幂等合同的超时写可能已经完成；框架无法替业务判定安全
- 问：轮询会平均负载吗？答：只均衡选择次数，处理成本、连接/权重、慢节点和热点可使资源负载不均
- 问：filter与业务事务有什么不同？答：filter管理调用上下文、校验和横切逻辑，不能自动为远端多个数据库建立同一事务
- 迁移：新增一个明确幂等的查询方法，并给它单独预算；写出只读与写方法不同重试策略的证据'''),
('04-resilience','04 限流、熔断与并发隔离','C10-04',
'''促销流量超过库存数据库容量，下游又开始间歇失败。系统应在入口按速率拒绝、按并发限制在途任务、按依赖失败触发熔断，不能用一个大线程池同时承担三种职责。''',
'''- 令牌桶允许容量范围内的突发，并按时间补充；滑动日志控制任意窗口接受次数，精确但需要保存记录
- 本地额度只对一个进程有效，扩容N倍不自动保持原全局额度。分布式限流还需处理共享计数原子性、时间与故障策略
- 熔断器基于观测结果决定是否允许后续调用，不负责限制并发；半开允许少量探测以判断恢复
- bulkhead隔离在途并发，拒绝应有明确返回，异常路径必须释放许可；线程池排队会消耗deadline
- 入口限流与bulkhead拒绝不算下游失败。本课组合顺序故意把它们放在breaker之外
- 指标必须区分主动拒绝、业务失败、网络失败、熔断拒绝与超时；把所有4xx计入失败率会误伤健康服务''',
'''请求 -> 本地令牌桶 -> 并发隔离 -> 熔断器 -> 下游
          |拒绝         |拒绝      |OPEN拒绝
          v             v          v
        速率超限      在途已满    不再压垮故障依赖
                                  |
                  CLOSED -> OPEN -> HALF_OPEN
                     ^                |
                     +---探测成功-----+''',
'''1. 用AtomicLong构造逻辑纳秒时钟，先耗尽容量2，再在499999999与500000000纳秒观察补充边界
2. 实现TokenBucket.allow；每次按已过时间补充且不超过capacity，同步保护复合读写
3. 实现SlidingWindow.allow，明确左开右闭窗口；用900毫秒突发说明固定窗口切换不能重置滑动日志
4. 组合真实Resilience4j breaker/bulkhead。4次受控失败打开，显式切半开触发2次成功再关闭
5. 用CountDownLatch保持2个在途请求，第3个立即拒绝，释放屏障后检查全部许可归还
6. 多线程共享一个容量7的令牌桶且时钟不走，80次尝试应恰好接受7次
7. 自己增加半开探测失败回到OPEN的断言，而不是用sleep猜测某一毫秒必须转换''',
'''两个限流器都是明确标记的T教学模型。breaker与bulkhead使用2.3.0真实库。状态机测试显式转换半开来隔离时间，不能把它说成自动定时转换实测。库配置仍保留10秒等待策略，真实负载定时行为需独立测量。''',
'''TokenBucket为O(1)每次请求，使用double存小数令牌，单位为纳秒且拒绝倒退时钟；极长运行跨度/数值精度不构成金融级精确计量。滑动日志空间O(limit)，每次被接受记录仅入队/出队一次，均摊O(1)。库包装顺序确保入口拒绝没有进入breaker统计；许可在finally释放。''',
'''- 问：限流、熔断和隔离可以互相替代吗？答：分别控制速率、故障后的调用策略、同时占用资源数，必须各自定义合同
- 问：半开越多探测越好？答：探测过多可能再次压垮刚恢复依赖，过少使恢复判断慢；按实例和全局探测量共同评估
- 问：本地限流10实例每秒100次是不是全局100？答：可能达到1000次，扩缩容和不均衡流量会改变实际值
- 问：滑动日志和近似滑动计数器如何选？答：日志精确但存储随额度增长，计数桶近似换取固定空间，必须说明边界误差
- 问：虚拟线程是否消除bulkhead？答：不能，数据库连接、内存与远端服务仍有容量上限
- 迁移：把入口额度按租户分配，并设计最大租户数/闲置清理，防止无限key把限流器本身撑爆'''),
('05-idempotency','05 持久化幂等、租约与重试预算','C10-05',
'''两个应用实例同时收到相同订单键。一个实例领取后崩溃，另一个稍后接管；旧实例又恢复。正确实现既不能二次扣库存，也不能让旧持有者凭已过期租约提交。''',
'''- 键作用域包含租户、业务类型与业务ID，参数指纹与键一起检查；同键不同参数应冲突而不是返回旧成功
- PENDING、COMPLETED与不存在分别代表处理中、已知终态、尚无法确认，不存在不等价“从未执行”
- 租约只是时间许可，代次/owner是拒绝旧执行者的栅栏；以数据库时钟比较租约，避免客户端时钟各说各话
- 库存更新和COMPLETED结果在同一个本地事务提交；外部支付副作用不在此保证之内，转到Saga/TCC
- 超时后按原键查询或重放结果，不重新生成键。已完成结果是该操作的原响应，不保证等于现在库存
- 重试包括尝试次数、总预算、每次剩余时间、可重试错误分类、指数退避和抖动；抖动分散同步重试但不增加容量''',
'''请求(key, fingerprint)
   |
 INSERT唯一键 + SELECT FOR UPDATE
   +--参数冲突-----------------> 拒绝
   +--COMPLETED----------------> 返回原结果
   +--PENDING且租约未过--------> BUSY
   +--过期---------------------> owner新值, generation+1
                                      |
                         本地事务检查owner/代次/租约
                         库存条件更新 + COMPLETED结果
                                      |
                                  COMMIT''',
'''1. 读Request校验与operations表结构，运行SQL合同测试观察OWNED、BUSY、REPLAY三条路径
2. 实现acquire：唯一键仲裁、锁定记录、参数冲突、数据库时间租约、接管代次递增
3. 实现complete：先验证持有者，再在同事务内条件扣库存与保存结果。库存不足保存-1这一稳定业务终态
4. 注入“库存更新后、结果提交前”故障，确认整个事务回滚且PENDING可在租约到期后接管
5. 强制实验记录lease_until=0模拟时间已到，旧owner即使恢复也不能提交。真实过期应由数据库时钟决定
6. 实现RetryBudget.execute，在固定种子随机源与逻辑时钟下验证预算递减、永久错误不重试、非幂等写不重试
7. 执行MySQL集成：8个并发同键只产生1个OWNED，重建服务对象仍能查询结果；关闭未提交连接观察真实回滚''',
'''H2仅验证SQL分支合同，不证明MySQL锁/断连语义。真实集成必须通过Docker MySQL。记录不会自动过期删除；生产保留期至少覆盖客户端重试/离线重放窗口，并有清理与审计约定。库存数值为实验整数，租约最大1分钟。业务写操作在本地数据库内，不能直接推广到任意外部副作用。''',
'''两次短事务分离领取和业务提交，避免跨外部等待一直持有库存锁。第二次事务锁定幂等行并验证owner+generation+lease，接管后旧worker失效。唯一约束是跨实例仲裁点。RetryBudget只捕获TransientFailure，永久错误直接传播；每次睡眠和重试都消耗同一个单调时钟预算。''',
'''- 问：Redis SETNX足够实现业务幂等吗？答：不能独立覆盖锁过期、数据库提交后响应丢失与去重记录持久性；应明确原子提交边界
- 问：只有租约为什么不够？答：暂停进程恢复可能继续写，必须在真正写入资源处检查栅栏，单纯“我还持锁”声明无效
- 问：幂等记录过期可直接删吗？答：删除后晚到重试可能再次执行；保留期、客户端最大重试期与业务唯一约束需一起设计
- 问：为什么同键不同参数要拒绝？答：返回旧结果会隐藏客户端错误，也可能把另一业务操作当成功
- 问：3层各尝试3次最坏多少？答：可达27次底层尝试；选择一层重试并传播预算，必要时再加共享重试令牌
- 迁移：把幂等作用域加入租户，补跨租户同key不冲突、同租户参数冲突和过期接管测试'''),
('06-transactions','06 XA、TCC与Saga真实恢复','C10-06',
'''库存与积分支付由不同数据库负责。数据库内事务不能自动覆盖两个服务。分别实现XA准备/恢复、TCC预留/确认/取消，以及可重放的Saga日志，比较资源锁、业务中间态与恢复责任。''',
'''- 2PC分为准备与决策两个阶段，参与者PREPARED后可能持锁等待；协调者必须先持久化决策再通知提交
- 本课用真实MySQL XAResource、两个MySQL实例与fsync决策文件，重建连接后XA RECOVER恢复；不是Java布尔变量模拟2PC
- TCC把业务资源显式预留，Try/Confirm/Cancel都需幂等；空回滚留下墓碑，晚到Try被拒绝，防止悬挂
- Saga每步是独立本地事务，补偿是另一次业务行为。中间态可见，补偿可能失败，也不能撤回已发短信或物理发货
- 本课Saga记录步骤，参与者独立数据库提交；丢失协调检查点后重试同一参与者键，避免二次扣款
- Seata/商业事务协调器适配不在此实现内：没有声称完成集群协调、日志复制、启发式决策、管理控制台或自动灾备''',
r'''XA：资源A PREPARE --+
                    +-> 协调日志 COMMIT + fsync -> A/B COMMIT
    资源B PREPARE --+          |
                              崩溃后按日志恢复；无决策则回滚

TCC：NEW -> RESERVED -> CONFIRMED
       \       |
        \      +-----> CANCELLED（重复取消不再加库存）
         +空回滚-----> CANCELLED（墓碑阻止迟到Try）

Saga：STARTED -> RESERVED -> COMPLETED
          \         \失败
           +------> COMPENSATING -> CANCELLED''',
'''1. 先运行TCC SQL合同测试，画available+reserved+sold守恒式；编码reserve与finish
2. 验证重复Confirm/Cancel、同键参数冲突、Cancel先到、Try晚到、Confirm之后不能用Cancel反向撤销
3. 编写Saga.step的状态推进。每个参与者成功后、协调日志更新前注入崩溃，重建Saga对象并继续
4. 在退款后、库存释放前再次注入故障，重试补偿应最终归还资源且不重复退款
5. 阅读XaTransfer中真实XAConnection与Xid，编码两个prepare、落盘决策、两个commit的严格顺序
6. Docker中执行两个MySQL资源：仅PREPARED没有日志时恢复回滚；已有COMMIT日志时恢复提交；重复恢复返回0
7. 记录PREPARED期间哪些资源仍可能持锁、人工恢复需要哪些证据。不得为了消除阻塞擅自对未知事务执行相反决策''',
'''XA是单协调者、每笔事务独立日志文件的受控实验。日志文件创建使用CREATE_NEW，禁止覆盖原决策；不能丢失/篡改日志后仍声称安全恢复。MySQL8.4默认支持prepare后detach，恢复账号需要XA_RECOVER_ADMIN。Saga为了简单串行化在一步内持有协调行锁跨参与者调用，故需有界超时并承认锁开销。正常完成表示“库存已预留、积分已扣”，发货确认属于后续业务。''',
'''TCC先用唯一分支行建立串行化点，再在同一个事务内改变库存与分支状态；Cancel不存在分支时插入墓碑。Saga每步的远端效果不和协调日志假装原子，通过参与者幂等键恢复“远端成功、日志未写”窗口。XA先让两个分支准备，只有持久化COMMIT以后才提交；恢复按格式ID和全局ID筛选，不触碰别的事务。''',
'''- 问：2PC为什么会阻塞？答：参与者准备后不能独立知道全局决策，协调日志不可用时可能等待并持有资源
- 问：TCC的空回滚和悬挂是什么？答：Cancel早于Try到达需留墓碑；随后迟到Try不能重新预留，否则取消后的资源又被占用
- 问：Saga补偿等于数据库rollback吗？答：不是，它是新的业务事务，中间状态可能被观察且外部副作用未必可逆
- 问：补偿失败是否可把Saga直接标为CANCELLED？答：不能，必须持久化待补偿状态、重试预算与人工处理入口
- 问：XA恢复为何要读日志而不是看两个余额猜？答：余额包含其他并发交易，不能推断本事务决策；启发式回滚会破坏原子性
- 迁移：增加第三个可失败参与者，写清逆序补偿、重复步骤、支付成功但通知丢失的恢复路径，并指出哪些效果不能补偿'''),
('07-outbox-cache','07 Outbox、幂等投影与有界缓存','C10-07',
'''库存数据库成功提交后需要通知搜索/页面读模型。直接“先写数据库再发消息”存在丢事件窗口；反过来也可能发布不存在的业务。发布器崩溃重启后会重复投递，读模型还可能把旧版本重新写回缓存。''',
'''- outbox与业务行在同一个MySQL事务写入，因此在数据库持久化假设成立时不会出现已提交业务没有待发布记录
- relay在Kafka确认后才标记published，二者不原子，确认后崩溃会重复；Kafka幂等生产不能消除应用重新send导致的新逻辑消息
- inbox与读模型在同一个消费端数据库事务提交，重复ID相同载荷被忽略，不同载荷必须报警；版本检查防乱序回退
- 消费数据库提交后、Redis失效前仍有窗口。重复消息也要再次执行失效，不能因inbox重复就提前跳过全部处理
- 缓存值有TTL，版本floor防止旧查询晚到回填。floor元数据长期保存，有明确键数量与清理成本；版本限制在2^53-1以内，避免Lua数值精度丢失
- 轮询简单可控，CDC减少扫描/延迟但引入日志保留、位点、schema演进和连接器运维。这里实现轮询，不把它冒充CDC''',
'''业务事务：[product revision+1] + [outbox e1] -> COMMIT
                         |
relay锁一条 -> Kafka ACK -> [published=1] COMMIT
                 |崩溃
                 +----重发e1（允许重复）

消费者：[inbox e1] + [read_model版本条件更新] -> COMMIT
                                            |
                                    Redis floor提高+失效
                                            |
                                       提交Kafka位点''',
'''1. 实现OutboxStore.change，把业务与事件同提交；库存不足时两者都回滚，相同eventId参数冲突拒绝
2. 实现publishOne，使用FOR UPDATE SKIP LOCKED分配待发记录，发送失败保留记录
3. 实现Projector.apply：inbox与读模型同事务，按revision只前进；运行乱序、重复、不同载荷和提交前失败测试
4. 编写两个Redis Lua脚本：fill拒绝低于floor版本，invalidate提升floor并删除更旧缓存；多个键在Redis Cluster中需同hash tag，当前单节点实验不宣称跨槽可用
5. Docker真实链路注入Kafka ACK后标记前崩溃，再启动新OutboxStore重发，消费到2条而投影只生效1次
6. 用旧版本回填验证floor拒绝；填入新值再等待TTL过期，检查空缓存而非把不存在当库存0
7. 写一致性边界：停止relay、Redis元数据丢失、数据库恢复旧备份分别会破坏哪个前提；不要写“延迟双删保证强一致”''',
'''保证为至少一次发布加幂等本地投影，不是端到端exactly once。成立条件：数据库已提交数据/outbox不丢、Kafka确认语义与副本配置满足要求、消费者持续重试、去重记录保留足够久。单broker测试不证明broker高可用。若缓存从主库读取且每次查询最长Q、缓存TTL为T，失效永久故障时旧值滞留可按Q+T估算；若从异步读模型填充，还要加已知投影延迟上界L，没有L就不能承诺有限陈旧度。''',
'''change先建立唯一事件键，再锁商品行算单调版本，保存完整投影值。relay一次锁一条并等待有界ACK，适合课堂直观说明失败窗口，吞吐扩展可改短租约批次但需重做崩溃合同。Projector通过条件更新抵抗乱序，不假设Kafka跨分区全序。Lua在单节点原子执行版本检查与写入，floor不随值TTL过期；Redis重建丢floor后暂时只剩TTL边界。''',
'''- 问：outbox是否让数据库和Kafka原子提交？答：没有，原子范围只有业务表和outbox；发布仍可能重复，消费者承担幂等
- 问：Kafka幂等生产后为什么还需inbox？答：应用重发、生产者重建、业务侧重复与不同协议边界仍可产生重复逻辑事件
- 问：只删缓存一次有什么竞态？答：旧查询可在删除后把旧结果写回；版本floor或受控TTL改变该窗口，但故障假设必须明确
- 问：最终一致有多久？答：仅“最终”不提供时间上界；需要事件积压、投影处理、查询时长与TTL的可测上限
- 问：轮询和CDC怎么选？答：按吞吐、延迟、数据库扫描成本和运维能力权衡；CDC仍需要位点恢复和幂等消费
- 迁移：增加按sku分区的多个发布器，乱序交付旧事件，验证版本不回退；再设计outbox/inbox清理与重放保留期'''),
('08-capacity','08 高并发库存、容量与故障答辩','C10-08',
'''把真实gRPC、Dubbo与同一持久化幂等库存连接起来。压测30个不同订单争抢10件库存，系统只成功10次；重复已成功订单不能再次扣减。设计评审还需要回答热点、分片、ID、异地、降级与回滚。''',
'''- 稳态近似Little定律：在途数≈到达率×平均服务时间；增加安全余量不是把平均值变成尾延迟保证
- 无队列准入让过载尽早显式失败。虚拟线程降低线程成本，不扩大数据库连接、锁和远端额度
- 单机额度乘以实例数才是集群上限，扩容前需按数据库共享池预算重新分配；超时和重试额外消耗资源
- 唯一ID位布局只是编码。工作节点号唯一、时钟回退、每毫秒序列耗尽和重启状态仍需要协议与持久化约束
- 按订单ID分片利于均匀写与点查，按用户/商家分片利于局部事务；热点sku库存可能仍集中，不能靠随机ID自动消除
- 库存不超卖是主库条件写不变量；列表可以允许陈旧，结算确认必须回主库。异地多写需要另定义库存额度分配或共识策略
- 回滚兼容不仅是代码：proto、幂等记录、事件schema、数据库字段和已提交外部效果都要能被旧版理解''',
'''30个客户端 -> gRPC输入校验 -> Admission(最多8在途)
                                      |
                              数据库幂等领取/重放
                                      |
                     UPDATE inventory ... available>=quantity
                                      |
                           库存+操作结果同事务提交

10件库存 -> 成功10个不同键 + 其余稳定拒绝
同键重放 -> 原操作结果，不再扣减''',
'''1. 计算1000请求/秒、平均80毫秒、1.5倍余量所需120在途；如果数据库分给本服务80连接，先限制额度并测吞吐
2. 实现Admission.execute，使用tryAcquire立即拒绝、finally释放；用屏障验证容量1时第二个请求不能进入
3. 实现IdLayout.compose并验证41/10/12位边界，解释相同节点号/时间/序列会碰撞，函数本身不分配节点租约
4. 运行网络+H2 SQL烟测，同键两次RPC只扣一次。明确这不是MySQL锁与恢复验证
5. 执行真实MySQL+gRPC集成，30个订单最多8并发争抢10件，断言成功10次、库存0、完成记录10条；再执行Dubbo+MySQL同键回放与参数冲突
6. 重放任一成功键，结果是最初那次响应，库存仍为0；关闭服务后确认资源退出
7. 完成故障矩阵与容量设计答辩：依赖宕机、缓存不可用、消息积压、注册中心失联、热点/扩容/回滚，逐项给证据和局限''',
'''端到端库存保证只覆盖一个MySQL主库内的库存与幂等结果；没有多主跨地域库存保证。准入是每进程上限，不自动提供公平性。SQL驱动与查询有独立超时，RPC取消不承诺立即中止数据库；未知结果仍按业务键恢复。集成测试规模用于验证性质，不是性能基准或生产容量证明。''',
'''DatabaseInventory把C10-05存储注入C10-02真实网络服务，DubboDatabaseInventory把完全相同业务合同适配到C10-03真实远程服务，整个业务调用受同一Admission保护。原子条件写防止库存变负，稳定保存不足结果防止同key以后意外成功。返回RESOURCE_EXHAUSTED表示入口容量拒绝，FAILED_PRECONDITION表示业务条件不满足，UNAVAILABLE表示暂时失败或未知结果需恢复。''',
'''- 问：如何证明不超卖？答：主库事务内条件更新只在available>=quantity时扣减，测试并发最后守恒；多主/跨分片需另证明
- 问：容量估算为何不能直接当压测结果？答：服务时间分布、锁竞争、连接建连、GC和热点会改变尾延迟，需要受控负载与监控复核
- 问：雪花ID是否天然全局唯一？答：位布局之外还需唯一worker租约、时钟回退策略、序列限额与重启状态，单个compose函数不保证这些
- 问：缓存挂了能否全部回源？答：直接全量回源可能打穿数据库，应准入、合并请求、分级降级并保护关键结算路径
- 问：如何扩展到异地？答：先选一致性目标与故障下可用性，可预分库存额度或单主/共识；代价是额度闲置、跨区延迟或分区时拒绝
- 迁移答辩：把单sku扩展为两sku订单，画锁顺序/死锁重试、跨分片事务与补偿路径；比较两种方案而非宣称唯一正确架构''')]

def write(path,text):
 p=R/path;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(text.strip()+'\n')
def finish():
 sources=json.loads((R/'authoring/source-verification.json').read_text()) if (R/'authoring/source-verification.json').exists() else []
 refs={item['repository']:item for item in sources}
 routing={1:['grpc/grpc-java'],2:['grpc/grpc-java'],3:['apache/dubbo'],4:['resilience4j/resilience4j'],5:['mysql/mysql-connector-j'],6:['mysql/mysql-connector-j'],7:['apache/kafka','redis/redis','redis/jedis'],8:['grpc/grpc-java','mysql/mysql-connector-j']}
 manifest=[]
 for index,item in enumerate(TASKS,1):
  name,title,unit,scenario,concepts,diagram,steps,contract,explain,questions=item
  base=Path('distributed-course/services')/name; path=R/base
  solution=path/'solutions';shutil.rmtree(solution,ignore_errors=True)
  for source in (path/'src').rglob('*.java'):
   if '/grpc/protocol/' not in str(source):
    target=solution/source.relative_to(path/'src');target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(source.read_bytes())
  fragments=[];files=[]
  for file in sorted(path.rglob('*')):
   rel=file.relative_to(path)
   if not file.is_file() or 'build' in rel.parts or file.name in ['task.md','task-info.yaml']:continue
   entry={'name':str(rel),'visible':True}
   if rel.parts[0]=='src' and file.suffix=='.java':
    text=file.read_text();holders=[]
    for match in re.finditer(r'(?<=// 练习区开始\n)(.*?)(?=\s*// 练习区结束)',text,re.S):
     holders.append({'offset':len(text[:match.start()].encode('utf-16-le'))//2,'length':len(match.group(1).encode('utf-16-le'))//2,'placeholder_text':('            // 请补齐状态迁移，空实现暂不修改状态\n' if match.group(1).lstrip().startswith('switch (event)') else '        throw new UnsupportedOperationException("请按本步骤合同完成实现");\n')})
     fragments.append(f'### {rel} 的练习实现\n\n```java\n{match.group(1).rstrip()}\n```')
    if holders:entry['placeholders']=holders
   files.append(entry)
  write(base/'task-info.yaml',yaml.safe_dump({'type':'edu','custom_name':title,'files':files},allow_unicode=True,sort_keys=False))
  links=[]
  for repo in routing[index]:
   entry=refs.get(repo)
   if entry and entry.get('status')=='verified':
    links.extend(f"- [{repo} {entry['tag']}：{f['path'].split('/')[-1]}]({f['url']})" for f in entry['files'])
  if index==1:links += ['- [TCP RFC9293](https://www.rfc-editor.org/rfc/rfc9293.html)','- [HTTP/2 RFC9113](https://www.rfc-editor.org/rfc/rfc9113.html)','- [PACELC原论文](https://www.cs.umd.edu/~abadi/papers/abadi-pacelc.pdf)']
  if index==6:links += ['- [MySQL8.4 XA状态与detach](https://dev.mysql.com/doc/refman/8.4/en/xa-states.html)','- [MySQL8.4 XA限制](https://dev.mysql.com/doc/refman/8.4/en/xa-restrictions.html)']
  source_text='\n'.join(links) or '源码验证正在执行，发布前必须回填固定提交；不得将当前标签入口称为验证通过。'
  write(base/'task.md',f'''# {title}

对应目录 {unit}。Java 21主线，本节可独立选择Gradle模块；依赖版本、完整源码与发布状态见课程首页。所有调用方、测试、数据定义和标准解直接可见。

## 企业场景

{scenario}

## 概念逐层建立

{concepts}

## ASCII机制图

```text
{diagram}
```

## 实际操作与逐步编码

{steps}

以下命令用于源码仓库/公开源码包；Academy官方ZIP内用Check/Run或Gradle工具窗口执行同名任务。官方导出可能剔除Wrapper脚本/JAR，不能假设导入目录能直接运行./gradlew。独立服务课需同源shared/versions.env快照，缺失时不能视为发行完成。

本节单元检查：`./gradlew :{name}:test`；完整调用端：`./gradlew :{name}:run`。含数据库/消息服务的单元另执行 `./gradlew :{name}:integrationTest`，Docker不可用应明确失败，不能跳过后当作通过。每次修改先跑对应方法测试，再跑全模块回归。

## 正确性合同与保证边界

{contract}

## 固定版本源码阅读

{source_text}

阅读任务：先在本节测试找到症状，再记录入口、关键状态、分支条件和返回/清理路径。每个结论附输入、版本、符号与反例。详细入口、关键状态、分支条件和实验证据对照见课程 docs/源码路线.md。源码字节哈希与标签解析结果在课程作者验证记录中公开；没有截图不伪称做过IDE断点。

## 公开完整标准解

完整Java文件位于本节 `solutions/`，与本节标准实现逐字同步，依赖接口、调用方和测试也在本节可见。下面列出全部编码区，便于先独立完成再核对；不需要解锁或另取私有分支。

{chr(10).join(fragments)}

## 标准解机制、复杂度与替代取舍

{explain}

## 面试机制、边界与深入追问

{questions}

## 三阶提示与独立验收

1. 基础提示：先列正常、边界、失败后的持久状态，找到测试的业务断言，不先复制实现
2. 机制提示：把每次外部提交、响应、日志落盘、资源归还画成独立事件，检查任意相邻事件间崩溃的后果
3. 深入提示：找真正执行原子操作的数据库/框架分支，确认幂等、锁、时间与持久化前提没有被内存模型替代

独立完成一个迁移题，补失败测试，解释一份错误实现被哪条断言拒绝，再做5分钟机制答辩。看过标准答案只记录“已阅读”，不能记录“独立掌握”。实际执行通过、未执行和已知边界见课程根中文阶段报告。
''')
  manifest.append({'name':name,'title':title,'unit':unit,'path':str(base)})
 write('authoring/manifest.json',json.dumps(manifest,ensure_ascii=False,indent=2))
 write('distributed-course/section-info.yaml',yaml.safe_dump({'type':'section','custom_name':'分布式服务与一致性','content':['services']},allow_unicode=True,sort_keys=False))
 write('distributed-course/services/lesson-info.yaml',yaml.safe_dump({'type':'lesson','custom_name':'从故障模型到企业恢复闭环','content':[t[0] for t in TASKS]},allow_unicode=True,sort_keys=False))
 additional=[]
 for folder in ['support','scripts','docs','gradle']:
  for p in sorted((R/folder).rglob('*')):
   if p.is_file() and 'build' not in p.relative_to(R).parts:
    entry={'name':str(p.relative_to(R))}
    if p.suffix=='.jar':entry['is_binary']=True
    additional.append(entry)
 for name in ['authoring/build_course.py','authoring/validate_course.py','authoring/verify_variants.py','authoring/materialize_learner.py','authoring/build_distribution.py','authoring/requirements.txt','authoring/manifest.json','authoring/source-verification.json','authoring/verify_sources.py','authoring/regenerate_proto.py','authoring/tools-lock.json','authoring/metadata-report.json','authoring/variants-report.json','authoring/callers-report.json','authoring/maven_read_proxy.py','authoring/prefetch_maven.py','authoring/resolve_cloud_dependencies.py','authoring/prefetch_gradle_metadata.py','authoring/dependency-metadata-evidence.json','authoring/dependency-lock-verification.json']:
  if (R/name).exists():additional.append({'name':name})
 for name in ['README.md','中文阶段报告.md','THIRD_PARTY_NOTICES.md','LICENSE-JetBrains-template','build.gradle','settings.gradle','gradle.properties','gradlew','gradlew.bat']:
  if (R/name).exists():additional.append({'name':name})
 write('course-info.yaml',yaml.safe_dump({'type':'marketplace','title':'分布式服务与一致性：RPC、治理与故障恢复','language':'Chinese','summary':'完整C10八单元，真实gRPC/Dubbo、MySQL持久化幂等、XA/TCC/Saga、Kafka Outbox与Redis缓存；验证边界见中文阶段报告。','programming_language':'Java','content':['distributed-course'],'environment_settings':{'jvm_language_level':'JDK_21'},'additional_files':additional,'yaml_version':2},allow_unicode=True,sort_keys=False))
if __name__=='__main__':finish()
