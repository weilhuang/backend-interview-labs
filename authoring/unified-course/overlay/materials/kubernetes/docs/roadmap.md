# C11完整路线与本批边界

本批是Docker→Kubernetes→Istio长期路线中的Kubernetes首批三课，不缩减原范围。

- C11-01 镜像、非root、PID1/TERM：前三课已有独立source草稿
- C11-02 Compose就绪、幂等初始化：沿用库存与Redis契约
- C11-03 容器DNS、连接/认证/协议定位：继续使用同一调用链
- C11-04 本批：Pod/Deployment/Service，三种探针，故障前后UID/重启数/EndpointSlice
- C11-05 本批：Service/DNS，ConfigMap环境快照与文件重读，合成Secret边界，RBAC正反授权
- C11-06 本批：requests/limits、滚动升级、坏版本阻断、明确revision回滚、Pending资源证据
- C11-07 待实现：PVC数据生命周期；在新卷恢复备份并比较业务值；具备执行能力的CNI下NetworkPolicy允许/拒绝双向实验
- C11-08 待实现：Istio按header确定性路由再到权重采样；应用+网格重试次数总预算；GET与幂等POST的差别
- C11-09 待实现：工作负载mTLS与用户JWT/业务授权两道门；STRICT明文拒绝、错误身份拒绝、允许身份成功
- C11-10 待实现：DNS/probe/OOM/policy综合故障定位；完整恢复闭环及清理；资源指标/CPU节流和HPA前提

后续还要补：有真实在途请求与TERM信号的排空E2E、原生Academy预览/学习者Check与失败标记传播、Gradle每module strict locks、双架构拉取和冷启动资源测量。它们不因有课文或脚本而自动完成。

Istio/CNI版本尚未冻结，必须以选定Istio发布支持的Kubernetes组合重新验证。当前Kind/Kubernetes pin仅用于本批三课，不提前声称将与未来Istio组合兼容。
