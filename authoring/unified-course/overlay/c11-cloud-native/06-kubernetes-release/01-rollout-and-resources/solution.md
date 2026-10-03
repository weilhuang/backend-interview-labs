# 标准答案与证据要求

完整答案在answers/deployment.yaml。核心策略为2副本、RollingUpdate、maxUnavailable=0/maxSurge=1、minReadySeconds=3、progressDeadlineSeconds=90、revisionHistoryLimit=3。API请求100m/128Mi，限制500m/256Mi。

请先估算峰值：稳定2个API，更新最多额外1个，因此光API请求就从200m/256Mi变为300m/384Mi。还有Redis、caller和控制面开销。设置maxSurge却不给容量，会把发布卡在Pending。

v2正确验收包括运行中的HTTP样本、版本标识和可用副本计数。broken负例必须看到目标Pod/live=200、/ready=503和Deployment的ProgressDeadlineExceeded，同时旧v2仍成功服务。随后显式回滚到保存的v2 revision，等待成功再看/info。超时命令不等于业务负例。

资源负例只改变受控Deployment的新模板CPU请求/限制，先根据节点allocatable证明必然不可调度。证据是Pending+Unschedulable+同Pod UID的FailedScheduling/Insufficient cpu。恢复原资源对象，再等发布和业务恢复。

等价工程方案可能采用蓝绿或canary，但本题练Deployment原生滚动语义，不要求你引入额外控制器。后续Istio课才讨论按头与按权重路由、实际重试次数及身份授权。本题不假装已完成这些高级内容。
