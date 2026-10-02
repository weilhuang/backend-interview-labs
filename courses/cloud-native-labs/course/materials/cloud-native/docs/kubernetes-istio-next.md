# C11-04..10 后续教学设计与安全入口准备

状态：DESIGNED，未实现、未创建集群、未运行Kubernetes/Istio。本文把Docker知识怎样延伸到企业场景说清，不把一堆未验证YAML当成完成的实验。版本、集群镜像、CNI与Istio兼容组合仍须先由总课程环境配置核验并固定。

## 先补词，再操作

- 集群：一组共同运行工作负载的节点；控制平面管理期望状态，数据面执行请求。它不是“很多Docker命令的别名”
- Pod：Kubernetes调度的基本工作负载单位；同Pod容器共享网络空间。因此它与“不同Compose容器的localhost”存在关键差异
- Deployment：声明想保持的副本和更新策略；控制器尝试让实际状态收敛到期望状态
- Service：给一组被标签选择的Pod提供稳定访问方式；selector错误会让Service找不到预期后端
- namespace：组织资源的范围，不是天然完备的安全隔离边界
- ConfigMap / Secret：配置与秘密资源。Secret的base64表示不是加密；避免把秘密写入日志和Git
- requests / limits：调度资源请求与运行限制，不能用“我写了limit”替代容量测试
- PVC：应用对持久存储的请求；删除容器与删除数据不是一回事
- CNI / NetworkPolicy：网络插件及流量规则；插件不执行策略时不能宣称隔离成功
- service mesh：工作负载间流量的统一代理与策略层；Istio控制平面下发配置，数据平面代理处理流量
- mTLS：双方证明工作负载身份并加密连接；不自动证明某个用户有下单权限

```
C11-01..03：进程 / 端口 / DNS / 就绪 / 持久数据
   |
   v
C11-04：Pod → Deployment → Service → 三种探针 → 排空
   |         |
   |         +--> C11-06：资源预算 / 滚动发布 / 回滚
   +--> C11-05：配置 / Secret / 最小RBAC
                 |
                 v
             C11-07：PVC / 恢复 / 网络隔离
                 |
C10重试预算 ------+--> C11-08：Istio路由 / 超时 / 重试放大
C15认证授权 ---------> C11-09：工作负载mTLS / 用户权限
                 |
                 v
             C11-10：DNS / probe / OOM / policy 排障闭环
```

## 安全执行入口先行

未来统一driver必须同时验证当前context、课程专属集群标识、namespace标签、目标资源UID；用户不熟悉时不让他们靠“应该是本地集群吧”猜。未知context返回INVALID_ENV并拒绝注入故障；只读kubectl版本/context查询可以用于定位。不会自动切换生产context，不扩大权限，不改宿主安全设置。

所有注入只命中特定run_id资源，并保存前态/后态。恢复不意味着删除用户PVC；恢复后还要业务契约通过。CNI不支持策略、metrics缺失、未注入sidecar、版本不兼容等分别记录INVALID_ENV/BLOCKED，不可用跳过测试凑PASS。

## C11-04：从一个Pod到可恢复服务

学习路径：先创建一个只含API的Pod并看状态；再通过Deployment表达副本意图；最后让Service访问它。每一步都用本项目网页/API看到结果。

需要新增的真实行为：有界启动延迟fixture；三端点分别反映startup/live/ready；SIGTERM排空与请求持续压测。现有/startup立即200只是第一批预留，尚不满足这课慢启动实验。

验收要点：杀掉一个课程副本，控制器补回；使ready失败，端点移除而容器重启计数不必增加；startup成功前不执行live/ready；滚动停止时已接受请求有明确结果。关键反例是下游一抖就liveness失败，导致恢复风暴。用重启计数和业务失败次数证明，不仅看YAML键存在。

官方起点：[三种探针](https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/)。源码锚点须待所选Kubernetes tag冻结后定位kubelet探针管理代码，当前不虚构行号。

## C11-05：配置和权限都要可解释

给API加入显式配置校验；演示环境变量变更通常要重建进程，文件挂载更新也需要应用明确定义重载。Secret只用合成值，测试日志不出现该值。

RBAC验证采用允许动作与拒绝动作双向断言：只读账号可读指定namespace资源，但不可写、不可跨namespace。禁用不需要的自动token挂载，不以cluster-admin掩盖权限问题。读到Secret不等于“安全配置已完成”。

## C11-06：坏版本不能只靠apply成功

使用两个明确业务版本和一个故意不能ready的版本；持续发送有request_id的请求，记录升级期间可用副本下界和业务响应。坏镜像/坏探针必须卡住发布而非报成功，再执行有范围回滚并确认旧响应恢复。

requests/limits先用固定压力实验解释，HPA只在指标链路齐备时执行；缺metrics必须BLOCKED。不要把权重、瞬时CPU或单次采样当容量结论。

## C11-07：持久数据和网络隔离

在新PVC里建立合成库存，重建应用后验证值；备份恢复必须落到另一个新卷，再比较业务结果，不覆盖原卷。说明StatefulSet本身不会替数据库完成数据复制。

NetworkPolicy测试先确认所用CNI支持并执行策略；用允许客户端/拒绝客户端分别请求API和Redis。无CNI能力时输出INVALID_ENV，不能仅凭kubectl apply返回0宣称隔离。

官方起点：[NetworkPolicy与插件约束](https://kubernetes.io/docs/concepts/services-networking/network-policies/)。

## C11-08：先确定路由，再看统计

第一阶段按请求头把固定调用路由到稳定版或canary，要求每个响应有版本标识。第二阶段才展示权重路由，收集足够样本并解释统计波动，绝不要求十次请求精确8:2。

重试fixture必须记录下游实际调用次数。应用和网格同时各重试两次可能放大总尝试数；按实际attempt计数检验总预算。GET与可能产生副作用的POST分开；幂等键不是随便重试所有POST的免责符。

官方起点：[Istio请求路由](https://istio.io/latest/docs/tasks/traffic-management/request-routing/)。实现前固定Istio发布版与对应Envoy版本，不能以latest标签开发后直接交付。

## C11-09：机器身份和用户权限是两道题

先看流量两端的工作负载身份，再启用STRICT mTLS。分别验证：允许身份成功、错误服务身份失败、非网格明文失败。然后给用户JWT策略和应用权限判断加独立用例。

RequestAuthentication校验提供的JWT，不应被误读成自动要求所有请求携带JWT；是否缺JWT也拒绝由显式授权策略决定。mTLS通过并不说明用户有某订单访问权。

官方起点：[Istio安全模型](https://istio.io/latest/docs/concepts/security/)。

## C11-10：一条有证据的因果链

故障库只有课程专属DNS、probe、OOM、policy四类，且每次注入都验证context和resource身份。学习者先按症状选择事件、容器日志、探针结果、资源使用和策略信息，再提出最小修复。

完整通过必须包含：注入前业务正常、指定故障确实发生、定位证据、修复动作、业务恢复、临时资源清单。重复重启、扩大所有超时、删卷重跑不能算修复。无法安全确认资源归属时必须停止注入，保留只读证据。

## 本批明确没有完成的事项

Kubernetes/Istio版本台账、集群创建、YAML参考/负例、原生Academy交互与真实集群测试均NOT_RUN。这里只交可评审的概念顺序、验收与安全合同，不能计入已完成课程单元数。
