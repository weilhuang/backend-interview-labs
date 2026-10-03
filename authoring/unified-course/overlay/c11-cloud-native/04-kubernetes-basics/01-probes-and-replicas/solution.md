# 标准答案与原因

完整文件见`answers/ProbePolicy.java`与`answers/deployment.yaml`，不是省略号片段。复制答案不是验收，仍要执行公开测试和真实集群场景。

Java核心：

```java
return !localFailure; // live：依赖坏了不杀本进程
return initialized && dependencyHealthy && seeded && !draining && !forcedNotReady;
```

另一种等价ready写法可用提前返回：未初始化/依赖异常/未seed则false；排空或强制未就绪则false；其余true。公开Java真值表检查行为，不要求某个字符串。

YAML的startup调用/startup，1秒周期×30次覆盖8秒合成初始化；ready调/ready；live调/live。三个端点名字只是本项目约定，平台只看配置与响应，不会猜端点含义。

实验证据应同时包含直接Pod ready=503、live=200、restartCount稳定、EndpointSlice少一个就绪UID、另一副本Service调用仍200。把readiness指向/live的错误解会缺失这些证据；让live依赖Redis的错误解会在下游中断时重启。

删除Pod后应找到新UID，旧UID不能仍算恢复；liveness实验则需要同UID的restartCount增加。恢复要重新检查业务而非只看状态绿灯。

本批没有实际运行TERM期间持续负载的排空E2E，源码给出了有界实现和测试设计，不能把本课探针PASS扩展成“所有优雅停机路径已验收”。
