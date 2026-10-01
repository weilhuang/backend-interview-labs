# C07-06 唯一token租约与资源端fencing

## 企业场景与进入条件

定时库存结算只能有一个有效执行者，但一个进程可能拿锁后被暂停，租约过期后其他进程已经完成写入。旧进程恢复以后仍握着Java变量，不能因此认为自己仍有权限。先理解C02线程暂停/取消、C06事务和C07-05复制故障。本节既实现真实Redis租约，也用真实MySQL资源端阻止旧序号覆盖。

A验证不能释放/续租他人锁、过期持有者写入被拒绝和取消释放；O解释时钟、暂停、复制与锁服务选择；R看SET NX和Lua路径。UUID锁token与fencing序号是两种不同信息，不能混用。

## 概念、例子与ASCII

```text
唯一token：证明“这是哪一次租约”，随机且不可复用
fence序号：证明“资源端见过更新的执行代次吗”，严格单调

正确授予：MySQL领fence=1 -> Redis SET NX PX成功 -> 绑定为FencedLease
         A暂停，Redis租期到
         MySQL领fence=2 -> B拿锁 -> 资源UPDATE WHERE accepted_fence<2
         A恢复写fence=1 ------------------------------> 拒绝

错误授予：A先拿Redis锁 -> 暂停过期 -> B领号并写入
         A恢复才领取更大的fence ----------------------> 错误地被接受！
```

SET key token NX PX把不存在判断和过期写入合成一次命令。release不能GET后再DEL，否则检查和删除之间锁可能过期并由另一人获得。Lua只在当前值等于本token时DEL；renew同理先比较token再PEXPIRE。即使renew成功，之后进程仍可能暂停，续租不是永恒所有权证明。

FencedResource持久保存accepted_fence，只有请求fence更大才更新。本课每个fence只允许一次写入，重复同一序号返回false；若一租约要多次写，应设计fence+操作序号、幂等键与响应重放，而不是随意把条件改成<=。

## 编码步骤与调用验证

1. 运行`./gradlew :redis:06-leases:run`，启动临时Redis/MySQL，观察资源接受一次写入、finally仅释放自己的租约。完成后容器关闭，无后台看门狗残留
2. 运行`./gradlew :redis:06-leases:unitTest`，检查空token与非正租期；编辑`src/labs/Leases.java`的`release`实现区，比较GET结果与ARGV token，匹配才DEL，返回布尔是否删除
3. 阅读并运行`wrongOrExpiredOwnerCannotReleaseOrRenewAnotherLease`：假token不能解锁；正常token可续租；用PEXPIRE 0确定性结束旧租约；新租约token不同；旧持有者无论解锁还是续租都失败，新租约仍在
4. 运行`./gradlew :redis:06-leases:test`的真实资源测试。`acquireFenced`必须先通过MySQL行锁递增领取序号，再尝试Redis租约；拿锁失败允许浪费序号。调用方必须使用返回的FencedLease，不得给旧租约重新领号
5. 看明确反例`counterexampleMintingFenceAfterLeaseAcquisitionIsUnsafe`：先拿锁、过期后才领号的旧持有者会得到更新序号，资源端竟接受。此处assertTrue是展示错误协议成立，不是标准方案认可该写入
6. 对照正确测试：A在暂停前已绑定f1，B获得f2并写入，A的f1被SQL条件拒绝；重复f2也按本课一次写契约拒绝。最后取消路径只解自己的token，不能直接DEL键

## 标准解逐步解释与安全边界

[完整公开标准解](solution.md)。令牌由UUID生成，每次尝试都是独立token；获取使用SET NX PX；释放/续期由Lua比较和修改，单次服务端执行不留客户端检查窗口。release是O(1)，锁争用不是公平排队，没有取得锁就明确返回空值，不无限自旋。

持久序列使用MySQL事务锁住唯一sequence行，读、递增、写、提交；这会成为扩展瓶颈，但让fence在Redis故障转移之后仍不回退。资源更新是一条条件SQL，把比较与结果写入合成数据库原子动作。资源端还必须持久保存已接受最高值，不能在应用重启时重置为0。序号授予和资源使用的权限在真实系统还需认证授权，本课假定所有调用者遵守协议，不能抵御恶意伪造一个任意大fence。

为什么不用同一Redis的INCR生成fence？在异步复制故障转移中计数器可能回退，单调前提被破坏。即使改用更强锁服务，外部资源也必须检查fence，否则旧客户端暂停问题仍存在。fencing不证明每一时刻都只有一个进程在计算，它阻止的是旧代次的有害资源写。

数据库领取在Redis拿锁之前，避免拿锁后暂停再领新号。它仍不是所有读写的线性一致业务事务，也不是原子“给Redis锁和MySQL序号一起提交”；失败会浪费序号，这是安全可接受的代价。旧请求已有较小序号时即便很晚才拿到租约，资源若已看到较大序号仍拒绝它，调用方需把拒绝当失效操作。

## 真实源码阅读路线

固定Redis **7.4.7** [src/t_string.c](https://github.com/redis/redis/blob/7.4.7/src/t_string.c)的`setGenericCommand`，定位NX已存在返回、成功设置键、过期状态写入；[src/eval.c](https://github.com/redis/redis/blob/7.4.7/src/eval.c)的`evalGenericCommand`解释比较token和删除为何不被其他命令插入。官方[分布式锁说明](https://redis.io/docs/latest/develop/clients/patterns/distributed-locks/)用于讨论不同故障假设，不把其中一种部署自动等同于本课两节点环境。

资源端fencing由`FencedResource.write`条件SQL定义，不属于Redis自带能力；R记录客户端调用、服务端条件、持久资源约束三个边界。源码路径已经核验，服务端断点证据另做。

## 面试问题、答案与递进追问

1. **锁值为什么要随机token？** 区分租约代次，旧持有者不能删掉后来者的锁；线程ID/固定主机名会重用，不能唯一标识每次获取
2. **GET后DEL有什么竞态？** GET后暂停到过期，别人获取新锁，再DEL误删。Lua消除检查修改之间的插入窗口，但不能阻止租期结束后的外部写
3. **续租够勤快能免fencing吗？** 不能保证进程不会暂停或网络分区。续租提高常态成功率，资源端最终验证才限制旧写
4. **为什么先发号再拿锁？** 反过来会让过期旧持有者在恢复后领取更新序号，骗过单调接收端。正确协议把代次在可能持有租约之前固定，失败可浪费序号
5. **fencing能用于所有外部系统吗？** 只有接收方能原子校验单调序号才成立。邮件、第三方API等若不支持此约束，需要幂等键、业务状态机或不同协调设计
6. **用锁还是数据库条件更新？** 若业务已落同一数据库，条件更新/唯一约束常更直接；跨资源锁增加可用性和故障假设，不能为展示技术而上锁

## 独立迁移与退出评阅

扩展为同一fence两次有序操作，增加operation_seq和重放响应，证明重复请求不重复扣减。写一条暂停时间线，分别放在领号前、拿锁后、资源提交后，解释各自结果。A要求真实Redis与MySQL断言，O要求授予顺序和故障假设，R要求真实分支；仅写SET NX或仅做Java锁模型不算完成。
