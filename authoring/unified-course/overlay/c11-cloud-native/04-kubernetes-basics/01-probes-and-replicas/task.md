# C11-04 从一个进程到会自愈的服务

预计90–120分钟。先修C11-01..03。目标不是背Pod字段，而是用真实响应回答：进程在跑、能接单、该重启，是不是同一件事？

## 1. 看懂最小系统

先读[共享项目入口](../../../materials/kubernetes/README.md)和[探针图](../../../materials/kubernetes/diagrams/probes.svg)。你已有完整Java HTTP订单API、Redis库存、网页和集群内Java调用方。无需重写数据库客户端。

- Pod像一个被一起安排工作的“小房间”；房间内共享网络，所以API的127.0.0.1可指自己
- Deployment像值班安排：期望两个副本，控制器发现缺一个会补一个；它不会保证你的业务代码正确
- Service像稳定前台号码：按标签找到后端，再结合就绪状态决定流量去哪里
- startupProbe问“初始化结束了吗”；readinessProbe问“现在能接单吗”；livenessProbe问“这个进程需要重启修复吗”

删掉Pod后得到新UID是补副本；同一个Pod UID下restartCount增加是容器重启。这两个观察不要混写成“服务重启了”。

## 2. 你打开题目时已有什么

```text
01-probes-and-replicas/
  ProbePolicy.java   待修改：live/ready的判断
  deployment.yaml   待修改：startup预算、readiness路径
  test/LabCheckTest.java  可见Academy桥，集成后才由Check执行
  answers/          完整可运行参考答案，卡住时可对照
  observations.md   记录真实实验结果，不填写想象的PASS
```

共享`KubernetesApp`调用ProbePolicy，再把true/false转成200/503。读到`handle`的前三个分支即可知道谁调用你的代码。`AppConfig`、库存Lua、HTTP响应实现已提供。标准参考慢启动8秒；启动期间/live也会503，正确startupProbe会延后liveness检查，防止应用还没启动就被重启。

## 3. 第一步，只改Java策略

打开ProbePolicy.java。当前错误写法把下游健康当作本进程存活，并把ready永远返回true。

补全规则：

1. startup只有initialized为真才通过
2. live只取决于局部进程故障localFailure；dependencyHealthy变成false不应导致重启
3. ready需要initialized、dependencyHealthy、seeded都为真，draining和forcedNotReady都为假

不要在纯策略里发Redis请求；状态采集在应用层完成，避免一次探针无限阻塞。公开Java测试枚举32组ready输入与4组live输入，合法的等价写法都应通过。

运行入口（把变量设为绝对路径）：

```sh
python "$PROJECT/bin/verify_java.py" --task C11-04 --task-dir "$TASK_DIR"
```

这是显式Java运行入口；本候选准备阶段未跑过它。你若没有JDK21，结果应是INVALID_ENV。

## 4. 第二步，改YAML让平台正确调用策略

检查deployment.yaml中selector和template.labels。selector不是备注，标签必须能匹配。再把readinessProbe路径改为/ready。startup失败预算要覆盖8秒初始化并留余量，例如1秒一次、30次；liveness仍连/live。

`terminationGracePeriodSeconds: 10`要覆盖已接受请求最多3秒的等待和JVM线程池关闭预算。它不是“保证所有请求都成功”的魔法，仍需真实信号测试；本批不把仅YAML存在当排空端到端通过。

```sh
python "$PROJECT/tests/check_task.py" --task C11-04 --task-dir "$TASK_DIR"
```

预期YAML_CONTRACT_PASS。故意恢复错误的/ live配置再跑，必须出现READINESSPROBE_ENDPOINT失败；这只检查配置合同，尚未证明平台执行行为。

## 5. 第三步，创建独立实验环境

按共享README整合唯一版本台账并预检，然后：

```sh
python "$PROJECT/bin/lab.py" up --versions "$LEDGER" --task C11-04 --task-dir "$TASK_DIR"
python "$PROJECT/bin/lab.py" observe
python "$PROJECT/bin/lab.py" call
```

`up`先等待Pod进程启动，从每个Pod的localhost执行幂等seed，再等Deployment就绪。为什么不是等Service就绪后才seed？因为ready需要seed，反过来等待会循环卡住。

看observe的两个UID、Ready和restartCount。call返回公开版本与配置。使用`open`和网页下单，再用同一个request_id重复，看到库存不重复扣减。

### 先比较一个没有控制器的Pod

打开共享manifests/pod-example.yaml，它是一份完整Pod，spec与Deployment的template.spec可以逐字段对照。运行：

```sh
python "$PROJECT/bin/lab.py" pod-demo
```

脚本在同一个受控namespace创建额外solo-orders Pod，直接访问其HTTP，确认没有controller ownerReferences，删除后再观察5秒内没有自动补回。这个短窗口观测配合无owner证据用于入门对照，不宣称任意外部控制器永远不会重建。随后下一节删除Deployment管理的Pod，会看到新UID出现。solo示例不加入orders Service的selector，结束即删除，不持续占资源。

## 6. 第四步，运行有证据的故障实验

```sh
python "$PROJECT/bin/lab.py" verify --scenario probes
```

公开脚本scenarios.py依次做：

1. 先证实两个副本Ready及业务请求成功
2. 让一个Pod的ready合成失败，直接访问它看到503；/live仍200，restartCount不变
3. 查EndpointSlice中该UID被移出就绪后端，另一个副本继续通过Service接请求
4. 恢复ready，观察同UID重新成为就绪后端
5. 把Redis Service暂时指向不存在标签，观测真实依赖断开；API ready失败但live仍200，无重启风暴；恢复原selector与业务
6. 制造单Pod局部live失败，观察同UID的restartCount增加并恢复。合成故障标记由应用启动时清除，明确不是emptyDir自动被清空
7. 删除一个已验证归属的API Pod，观察新UID补回且服务恢复

不接受“apply成功”“Pod是Running”或“请求连不上，说明负例成功”。每个故障有前置健康、指定观测、恢复后置。环境缺失不能算业务失败。

## 7. 常见卡点

- Running却不Ready：先看/ready和seed，不先重启所有Pod
- 第8秒前反复重启：startup预算不够，或把liveness当初始化轮询
- Redis暂断造成所有API重启：把下游写进liveness，恢复时反而加大压力
- Service没有后端：先看selector/labels，再看readiness；不是先怀疑DNS
- startup已成功后又失败：startupProbe成功后不会继续像readiness一样每次决定路由
- 无Docker、错误context或权限错误：INVALID_ENV，修环境后重跑，不能写预期负例通过

## 8. 面试追问与工程取舍

1. readiness失败为什么不自动重启？重启不一定解决下游故障，移出路由让服务有机会恢复
2. readiness是否应该包含所有下游？只纳入服务履行其核心契约必需的能力；可降级依赖不一定阻断全部流量
3. liveness有什么危险？过于敏感会把瞬时抖动放大成重启风暴；太宽松又修复不了死锁，需要明确故障模型
4. 两副本在一个kind节点上是不是高可用？能练控制器，但节点故障仍会一起不可用
5. Pod删除与Deployment删除有什么不同？删除Pod会被控制器补回；删除Deployment改变了控制器/所有权关系
6. 为什么port-forward不能证明服务负载均衡？它建立到特定后端的隧道；用集群内caller观察Service路径

完成后填写observations.md。按需down，只删除本次随机run集群，不清理其他集群或镜像。

## 官方参考核对

[Kubernetes 存活、就绪和启动探针](https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/)。对照三类探针各自控制的行为，避免把下游故障等同于本进程死亡。

链接用于核对概念和 API；本文的固定依赖版本、公开测试及答案共同定义练习，不把官网最新示例自动升级为课程版本。
