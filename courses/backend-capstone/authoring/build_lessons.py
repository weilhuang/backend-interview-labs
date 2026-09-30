from pathlib import Path
import json,re,yaml
R=Path(__file__).resolve().parents[1]
def put(path,text):
 p=R/path;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(text.strip()+'\n')
chapters=[
('01-contract','OrderRules','01 需求、状态机与业务不变量',
'''你接到的需求是“一个商品可以被并发下单，取消归还库存，下游最终看到订单状态”。先把它变成可反驳的合同：相同请求号、相同商品和数量返回原结果；同号改参数必须冲突；库存不能为负；取消最多释放一次；收到旧消息不能把取消变回预留。RESERVED只是资源预留，尚无真实付款或出库，因而本阶段的取消可以直接补偿库存。本模型没有自动到期取消；客户端超时只表示结果未知，不会自动归还库存。

容量假设是单机MySQL、20件初始商品、一次1–100件、8个数据库连接。Kafka只有一个教学broker；没有集群容灾或全球唯一身份保证。请求号区分大小写，禁止空白、斜线和控制字符；数据库仍显式使用utf8mb4_0900_bin，不能靠输入规则代替存储规则。

完成validate、sameRequest、mayCancel三个学习区，保留其余完整调用代码。先写合法边界，再写换参数和重复取消。不要把参数检查只放到前端，也不要以重新创建订单的方式处理重试。''',
'''创建 Command("req-01","book",2)，通过验证；构造已取消订单，再用相同参数调用sameRequest，必须得到原CANCELLED对象。用数量3重试必须抛Conflict。运行本节Usage，观察事件号req-01:1与订单版本对应。''',
'''未出现 --下单事务--> RESERVED(v1) --取消事务--> CANCELLED(v2)
                   | 原号原参数重试            | 重复取消
                   +----原结果----------------+----不再释放
同号换参数 --> 409；未知响应 --> 原号查询/重试；不能改用新号''',
['把“合法请求”“重复意图”“取消状态迁移”拆成三种判断，异常含义也应分开。','数量下界1和上界100都包含；请求号保留大小写，不做trim或toLowerCase。','已有订单是最终判断依据。取消后重复下单不能把状态重置为RESERVED。'],
'''从[OpenJDK21的Objects.requireNonNull](https://github.com/openjdk/jdk/blob/jdk-21%2B35/src/java.base/share/classes/java/util/Objects.java)追踪空引用检查；在OrderRules.validate与sameRequest打断点。分别输入null、数量0、已取消订单和同号不同商品，记录哪一分支拒绝，异常类型为何不同。源码并不会替你定义业务幂等，合同是本课程自己的领域设计。''',
[('机制：为什么需要请求号，订单自增ID不够吗？','请求号标识客户端的业务意图。服务端自增ID在响应丢失后无法让客户端知道此前那次是否已提交。'),('边界：用同一请求号改变数量怎么办？','校验已经保存的商品与数量，拒绝参数冲突；不能返回成功却偷偷忽略新参数。'),('取舍：库存不足是否也永久保存为幂等结果？','本实现回滚失败请求，补货后原号可能成功。若业务要求失败也固定，需新增持久失败状态及结果合同，不能只改错误文案。'),('追问：超过一天的请求能否删除去重记录？','先定义客户端重试窗口和事件保留窗口，再设计归档；删除后旧请求可能再次执行。')]),
('02-reliability','OrderService','02 MySQL事务、并发库存与缓存边界',
'''这一步把业务合同落到真正的持久化边界。插入唯一请求、条件扣库存、追加outbox必须在同一个连接和事务内完成。UPDATE inventory SET available=available-? WHERE available>=?把检查与扣减结合；先查库存再在Java里减，会在并发下破坏不变量。

遇到MySQL1062只代表请求身份已经存在，不能吞掉所有SQLException。先回滚当前事务，再锁读已有订单并比较参数。库存不足和写outbox失败都回滚订单与库存。取消锁住订单行，第一次取消归还数量、迁移版本并追加事件；重复取消直接返回。不得在这个数据库事务内做Redis、Kafka或RPC网络调用。

缓存采用旁路读取和提交后尽力失效，TTL为5秒；失败时回源。并发旧读回填仍可能短暂出现旧值，因此这个策略不宣称强一致。fresh=true、库存判定和审计都走MySQL。请实现place与cancel两个学习区，然后增加一次outbox约束失败的回滚测试。''',
'''启动本检查点后，用页面原号提交2件、再提交一次；库存只下降2。改数量3观察409。缓存查询一次后取消，强一致查询立即CANCELLED。运行真实集成时40个不同请求争抢16件剩余库存，只有16个成功；缓存停止后取消仍能提交。''',
'''事务开始
  唯一订单身份 -> 条件扣库存 -> outbox事件 -> COMMIT
       |冲突            |不足          |失败
       +--> 查原结果     +------ ROLLBACK -----+
COMMIT之后：缓存失效 / HTTP应答可能丢失；业务事实不回滚''',
['先让所有写入共享同一个Connection，关闭自动提交，并给每条失败路径安排rollback。','唯一键冲突不能证明参数相同；回滚后用FOR UPDATE读取已提交结果。','取消必须先锁订单再归还库存。缓存失效和故障注入放在commit之后。'],
'''阅读[Spring6.2.19 DataSourceTransactionManager.doBegin/doCommit/doRollback](https://github.com/spring-projects/spring-framework/blob/v6.2.19/spring-jdbc/src/main/java/org/springframework/jdbc/datasource/DataSourceTransactionManager.java)与[MySQL8.4 InnoDB锁说明](https://dev.mysql.com/doc/refman/8.4/en/innodb-locking.html)。本实验故意使用显式JDBC事务暴露边界，不声称用了@Transactional。对照源码中的autoCommit切换，在place的executeUpdate、commit与rollback打断点；记录outbox写失败时三个表都不改变的证据。EXPLAIN订单主键查询与outbox_pending索引查询，解释唯一查找与批量扫描的区别。''',
[('机制：事务为什么不能跨HTTP与Kafka自动生效？','本地数据库事务只能约束该连接上的数据库修改，远端确认是另一个持久化边界。'),('边界：commit成功但客户端没收到200怎么办？','保留原请求号查询或重试；同号参数校验返回原状态。超时只表示客户端不知道结果。'),('取舍：为什么不用Redis分布式锁防超卖？','库存事实在MySQL，条件更新和约束直接保护它；加锁不能替代事务，反而增加租约过期窗口。'),('追问：8连接池够不够？','先测事务持有时间、到达率、竞争热点与超时，再给容量依据。这个数字只是课堂预算，不是生产推荐。')]),
('03-delivery','DeliveryFlow','03 Kafka、gRPC与每个确认窗口的重放',
'''异步链路包含三种不同事实：订单数据库已经提交；Kafka已确认消息；接收端inbox和配送读模型已经提交。任何一条网络应答都可能丢失。Kafka生产者幂等只处理生产者会话内的重试，重新创建生产者再次发布同一业务事件仍可重复。

先区分“客户端配置不合法”与“broker暂时不可用”：KafkaAdminClient构造时要求default.api.timeout.ms不小于request.timeout.ms。创建主题与位点检查统一使用总API预算5秒、单请求2秒；健康检查总预算1秒、单请求0.5秒，外层等待和关闭也有界。BrokerConfigTest在没有Docker的环境直接构造真实Admin，既复现旧配置异常，也验证两种正式配置；不能等到拉起容器才发现这个合同。

本节实现publishOne与consumeOne，要求先完成业务效果再推进确认。生产者收到Kafka确认后才更新outbox.published。消费者等待gRPC成功后，提交该分区record.offset()+1。接收端先写inbox唯一事件号，再更新读模型，二者同事务。相同事件号不同载荷拒绝；版本2的取消到达后，版本1的预留不得回退读模型。

Checked回调是为了对“效果/确认顺序”做可控单元测试，真实调用方仍是KafkaProducer、KafkaConsumer和生成的gRPC stub。真实传输、MySQL唯一键、超时后重放由integrationTest单独证明。完成后保留一张故障窗口表，不能把单元替身的通过写成真实MQ证明。''',
'''执行place→publish→consume，检查outbox变已发布、inbox一条、读模型RESERVED。打开AFTER_KAFKA_ACK后第一次发布抛Unknown，但Kafka已经有记录；再次publish和consume最终仍只有一条inbox。再在接收端提交后丢失RPC应答、在RPC确认后丢失Kafka提交，各重放一次。''',
'''订单事务     outbox       Kafka日志       gRPC接收事务       消费位点
  commit ------>| --send--->| --poll---> [inbox + 读模型] ----> commit(n+1)
                |   A应答丢失      B超时未知      C应答丢失
                +--可重复发布------+--可重复调用----+
                       唯一事件号 + 载荷一致 + 单调版本''',
['把send/mark和rpc/commit分别当作有顺序的两个操作；前一个失败时后一个绝不能执行。','故障注入必须放在效果成功之后、确认之前，才能真正暴露未知窗口。','Kafka位点是下一条要处理的位置。不要批量提交尚未完成的记录，也不要启用自动提交。'],
'''在[Kafka3.9.1 KafkaConsumer.commitSync](https://github.com/apache/kafka/blob/3.9.1/clients/src/main/java/org/apache/kafka/clients/consumer/KafkaConsumer.java)与[gRPC1.71.0 ClientCalls.blockingUnaryCall](https://github.com/grpc/grpc-java/blob/v1.71.0/stub/src/main/java/io/grpc/stub/ClientCalls.java)定位确认与异常边界；再检查[KafkaAdminClient.calcDefaultApiTimeoutMs](https://github.com/apache/kafka/blob/3.9.1/clients/src/main/java/org/apache/kafka/clients/admin/KafkaAdminClient.java)的预算校验。阅读[gRPC deadline说明](https://grpc.io/docs/guides/deadlines/)。断点分别放在DeliveryStore.commit、RPC返回和consumer.commitSync，故意让前一位置完成而后一位置失败，记录数据库行数与消费组位点。此实验是一个broker，不覆盖副本选主。''',
[('机制：inbox为何必须与业务写入同事务？','先记录inbox后业务失败会永久丢失效果；先业务后去重失败会重复执行。'),('边界：gRPC DEADLINE_EXCEEDED能直接补偿库存吗？','不能，服务端可能已经提交。先按事件号重放或查询，不能把未知结果判定为失败。'),('取舍：为什么不做跨MySQL与Kafka的XA？','outbox把原子性缩在本地数据库，接受重复和短暂延迟，换取可恢复的异步边界；不是消除了复杂性。'),('追问：遇到永久非法消息会怎样？','本轮消费中止、失败位点不提交，其他分区也可能暂时受阻；保留证据供人工修复或审核后隔离。生产化需要有审计的隔离队列策略，不能悄悄跳过。')]),
('04-recovery','RecoveryPolicy','04 Compose健康、持久化恢复与事故证据',
'''本阶段把业务决策、依赖健康和恢复动作分开。MySQL不可用就不能可靠接单；Redis失败可绕过缓存；Kafka或gRPC失败时预算内可先写outbox。待发布事件和投影落后订单均纳入观察水位，达到1000时HTTP拒绝新单，取消仍可执行。这个水位是并发下的软准入阈值，不是跨节点精确计数配额。

实现decide并写阈值前后测试。Compose启动时等待依赖健康；运行中不能把“进程还活着”当作业务就绪。/api/ready检查数据库与积压，/api/health分别显示四项依赖。停止某个服务后页面应保留未知/失败状态，不能继续显示旧的绿色结论。

scripts/course.sh只按当前课程路径生成Compose项目名，stop不删卷，没有reset或down -v。Mac和Linux共用Docker Compose命令，完全不扫描PID，不会pkill系统Java。真实恢复脚本与CI必须读取根infra/versions.env七个键。修改共享版本台账是另一项版本变更，不能在本课偷偷换镜像。''',
'''先scripts/course.sh start。提交一单但不重放，记录库存、outbox和订单号；pause-service mysql后请求应失败，recover-service mysql后同号查询恢复。再暂停delivery，发布后RPC失败；恢复delivery再重放，投影追平。每次只操作当前项目的命名服务。''',
'''发现：RPC红色 + 投影落后
  -> 假设：订单未丢失，接收端不可用
  -> 验证：MySQL订单/事件存在，RPC探针失败
  -> 修复：恢复delivery，不删除队列和表
  -> 回归：重放原事件，inbox不重复，审计无ERROR
  -> 记录：版本、命令、时间、结果、尚未覆盖项''',
['先判断数据库，再判断积压边界，最后判断可降级的依赖；顺序表达业务优先级。','pending等于limit也应拒绝，不是只有超过才拒绝。缓存故障不应改变库存事实。','重启保留卷；Testcontainers随机映射端口可能变化，因此恢复探测重新inspect端口。'],
'''阅读[SpringBoot3.5.16 ApplicationAvailabilityBean](https://github.com/spring-projects/spring-boot/blob/v3.5.16/spring-boot-project/spring-boot/src/main/java/org/springframework/boot/availability/ApplicationAvailabilityBean.java)。框架的生命周期状态不等于本项目的积压和依赖合同；本课另设业务探针。检查HealthMain的超时、RecoveryPolicy阈值，以及RealServices.restartMysql的端口重新发现。拿一次真实故障记录说明“启动成功”“存活”“就绪”“业务追平”的区别。''',
[('机制：为什么Redis坏了还能接单？','缓存不是事实存储；事务仍在MySQL完成，代价是回源负载变大。'),('边界：重放后outboxPending为0是否说明业务完成？','不一定，事件已进Kafka但接收端可能落后，还要看投影版本、inbox与业务审计。'),('取舍：为什么不自动清理积压？','清空会丢失已提交的业务意图。应限流、恢复依赖、按同一身份重放，保留人工处置证据。'),('追问：单机卷保留是否等于灾备？','不是，宿主机或卷损坏仍可能丢数据；副本、备份恢复和跨可用区属于另外的验证。')]),
('05-defense','Audit','05 盲测变体、库存审计与2/5/15分钟答辩',
'''这一阶段把“测试绿了”改成“能说明为什么成立，哪里尚未证明”。实现Audit.inspect：每个商品可售库存加所有RESERVED数量必须等于初始库存；取消订单不占用；不存在的商品、负库存、无来源投影、同版本冲突或超前投影都是ERROR；缺少或旧版本投影是LAG。累计数量使用long，报告只读。

生产页面从MySQL同一REPEATABLE READ事务读取审计快照，避免把不同提交时刻的库存和订单拼成假错误。健康状态和积压数是另一次观察，不构成跨服务原子快照。课堂共享一个MySQL实例但订单与配送用不同事务和进程，没有共享RPC事务。

先独立完成审计，再运行scripts/draw-defense.py抽取一个故障、一个新需求、一个设计问题。可见答案一直开放；“盲测”指你在作答前主动不看答案，不代表隐藏测试或强制解锁。把新变体回归写进本节test，产出事故记录与口述稿，不只复述标准答案。''',
'''先制造读模型落后，审计只能报LAG；完成重放后变为空。再在独占测试容器中故意减一件库存，审计必须报ERROR。用固定种子生成100组预留/取消组合做性质检查。最后抽题，把“客户端超时后换新请求号”作为反例解释双扣风险。''',
'''数据事实 -> 同一快照 -> 不变量审计 -> 证据表 -> 面试陈述
                      | LAG：可重放      | ERROR：停止猜测
                      +------定点验证----+
2分钟：问题/不变量/结果
5分钟：加事务与确认窗口
15分钟：加源码、故障证据、替代方案、未验证边界''',
['先按商品累计仍占用的数量，再检验库存守恒，不要把CANCELLED也加进去。','比较订单版本与投影版本：缺失/落后是LAG，超前/同版本异态是ERROR。','用long累计，并测试投影没有来源订单；输出不可变集合，审计不应自行修复数据。'],
'''阅读[OpenJDK21 HashMap.merge](https://github.com/openjdk/jdk/blob/jdk-21%2B35/src/java.base/share/classes/java/util/HashMap.java)与[MySQL8.4一致性非锁定读](https://dev.mysql.com/doc/refman/8.4/en/innodb-consistent-read.html)。本课使用HashMap做O(n+m)审计，不宣称它提供数据库一致性。对照Database.snapshot中的同一Connection与事务，在另一个连接提交订单，记录事务中多次普通SELECT看到的版本；再说明为什么跨库一致快照需要另外的设计。''',
[('机制：审计发现不守恒能直接把库存补回吗？','不能，可能存在漏记、重复扣减、错误快照或未建模业务。先保留证据定位原因，自动补数会掩盖问题。'),('边界：所有公开用例通过就能宣布生产可靠么？','不能。只覆盖给定版本、拓扑、负载和故障点；要报告真实运行过的项目和没有验证的边界。'),('取舍：为何共享一个MySQL实例？','降低学习环境资源成本，仍保持本地事务与RPC确认的分离；独立库故障域和容量隔离要另外部署验证。'),('追问：如何诚实讲项目经验？','说“我在隔离实验用这些版本复现了这些故障，并用这些断言验证”，不要改写成生产用户数或从未经历的事故。')])]
for stage,target,title,body,usage,diagram,hints,source,questions in chapters:
 path=f'capstone/stages/{stage}'
 code=(R/f'{path}/src/labs/capstone/{target}.java').read_text()
 text=f'''# {title}\n\n## 本节要交付什么\n\n{body}\n\n## 先运行完整调用方\n\n{usage}\n\n从课程根运行 `./gradlew :{stage}:test :{stage}:usage`。实际数据库与网络验收用 `./gradlew :{stage}:integrationTest`，需要Docker。完整网页调用用 `CAPSTONE_STAGE={stage} scripts/course.sh start`。所有测试和调用方都可见；不需要先抄完其他阶段的学习区。\n\n```text\n{diagram}\n```\n\n## 完整项目在哪里\n\n本节只替换 `src/labs/capstone/{target}.java`。公共应用在 `app/src/main/java/labs/capstone/`，中文页面在 `app/src/main/resources/static/index.html`，其他已完成依赖在公开 `reference/src/labs/capstone/`。Gradle显式排除本节对应的reference同名类，防止测试绕过你的实现。`test/`与`integration-test/`是本节测试；`shared/`是可见的公共测试支撑。根README给出完整结构、接口与启动依赖。\n\n## 逐步动手\n\n1. 在纸上写出本节的失败分支，先预测每次调用是否允许推进状态\n2. 运行现有测试，逐个实现学习区；为一个边界补充可见测试\n3. 用Usage或页面实际调用，再运行真实集成；记录编译、快测、容器、浏览器各自结果\n4. 不看下方答案，解释一个错误实现为什么会被你的新测试拒绝\n\n## 递进提示\n\n'''
 for i,h in enumerate(hints,1):text+=f'{i}. {h}\n'
 text+=f'\n## 核心源码与断点证据\n\n{source}\n\n## 面试递进\n\n'
 for q,a in questions:text+=f'**{q}**\n\n{a}\n\n'
 text+='## 标准答案与解释（直接可读）\n\n下面是完整作者实现，不依赖折叠渲染或解锁。先对照关键分支，再重新独立实现；公开答案不会被导出排除。\n\n```java\n'+code+'```\n\n'
 text+='为什么这样实现：前面定义的业务状态、失败边界与源码分支必须对应到代码；每次确认都只能声明它前面的效果已经完成。测试既检查返回值，也检查持久化事实和不会发生的副作用。模仿代码排版不是目标，能用不同写法维持相同合同才算通过。\n'

 if stage=='01-contract':
  text=text.replace('实际数据库与网络验收用 `./gradlew :01-contract:integrationTest`，需要Docker。','本节只验证领域合同，没有独立容器用例；不要把本节integrationTest零测试当作联调。真实MySQL从02-reliability开始，Kafka与gRPC持久化从03-delivery开始。')
 put(path+'/task.md',text)
 files=[]
 for f in sorted((R/path).rglob('*')):
  if f.is_file() and not any(x in f.parts for x in ['build','.gradle']) and f.name not in ['task.md','task-info.yaml']:
   item={'name':str(f.relative_to(R/path)),'visible':True}
   if f.suffix=='.java' and f.name==target+'.java':
    placeholders=[]
    for m in re.finditer(r'        // 学习区开始\n(.*?)        // 学习区结束',code,re.S):
     content=m.group(1);offset=len(code[:m.start(1)].encode('utf-16-le'))//2
     placeholders.append({'offset':offset,'length':len(content.encode('utf-16-le'))//2,'placeholder_text':('        result = Exercise.unimplemented();\n' if target=='OrderService' else '        return Exercise.unimplemented();\n' if target in ['RecoveryPolicy','Audit'] or (target=='OrderRules' and len(placeholders)>0) else '        Exercise.unimplemented();\n')})
    item['placeholders']=placeholders
   files.append(item)
 put(path+'/task-info.yaml',yaml.safe_dump({'type':'edu','custom_name':title,'files':files},allow_unicode=True,sort_keys=False))
put('capstone/section-info.yaml',yaml.safe_dump({'content':['stages'],'custom_name':'C14 后端综合项目'},allow_unicode=True,sort_keys=False))
put('capstone/stages/lesson-info.yaml',yaml.safe_dump({'content':[c[0] for c in chapters],'custom_name':'五阶段业务闭环与答辩'},allow_unicode=True,sort_keys=False))
put('authoring/manifest.json',json.dumps([{'module':c[0],'target':c[1],'title':c[2]} for c in chapters],ensure_ascii=False,indent=2))
