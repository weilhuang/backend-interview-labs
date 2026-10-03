# 先找到故障层，再做最小修复

## 本批实际实现的观测

- selector错误：Pod仍Ready，但Service EndpointSlice没有Ready后端；还原selector
- readiness合成失败：直接Pod为503、live为200、同UID重启计数不变；移除指定故障标记
- Redis Service断开：真实TCP依赖不可用，API不能Ready；只恢复Redis selector，不重建Redis、不回填库存
- liveness局部故障：同Pod UID容器重启计数增加；应用重建清除合成标记，之后验证Ready与业务
- 坏版本：指定Pod的ready=503/live=200，Deployment进展超时；回滚到保存的已验证revision
- 资源请求不足：新Pod Pending/Unschedulable，匹配UID的调度事件说明Insufficient cpu；还原受控Deployment原resources

每次有前置健康、目标身份、负例证据、恢复与后置HTTP。没有匹配证据时FAIL或INVALID_ENV，不能拿通用异常凑成功。

## OOM与节流：本批只讲机制，没有制造该故障

Pending说明调度未满足，通常还没有业务容器；OOMKilled是容器终止原因，需要关联lastState.terminated.reason、exitCode、restartCount、memory limit及应用内存来源。Exit137本身不足以断言OOM，强制SIGKILL也可能是137。

Java -Xmx只管堆，不含线程栈、Metaspace、JIT code cache、直接内存和JVM本身。先看内存趋势与请求特征，再判断泄漏、并发预算、堆外使用或limit过低。盲目把limit变大可能只是把问题推迟。

CPU limits可能导致节流和延迟增大，不一定重启；requests影响调度和竞争份额，并不等于绝对独占。需要容器CPU/节流指标、请求延迟和并发数据，不能把单次kubectl top当容量结论。

下一阶段将用有界内存fixture和具备指标链路的环境分别验证OOM与throttling，必须先确保不会冲击宿主。本批禁止在学员机器上做无界内存申请。

## 不安全或无效的修复

- 删除所有Pod/namespace，丢掉原始证据
- 扩大所有超时掩盖错误地址或认证失败
- 把所有账号变成cluster-admin
- 删除PVC重建后声称数据已恢复
- 未确认CNI能力就凭NetworkPolicy YAML宣称网络已隔离
- 把缺Docker、超时、无权限当成预期故障成功

## 创建中断如何处理

driver创建前持久化随机run，再创建独立Kind。若处于CREATING且尚未保存node_id/namespace_uid，正常down会拒绝，因为没有足够归属证据。请保留本次非秘密run标识并让维护者核对该随机名称的创建记录与Docker标签，补足身份后做限定清理；不要照网上命令全局删集群或prune。自动中断恢复目前未实现，不算PASS路径。
