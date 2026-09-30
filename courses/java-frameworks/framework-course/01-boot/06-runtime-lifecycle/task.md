# 06 生命周期健康与优雅关闭

对应完整课程：C04-06。JDK 21，Spring Boot 3.5.16 / Framework 6.2.19。先修和运行方法见课程首页；本节全部源码、调用方、测试和标准解公开。

## 企业场景

服务停机时应停止接单，并在有限预算内处理已有任务。健康状态必须表达真实资源状态，而不是永远返回UP。

## 实际操作与逐步编码

1. 运行Usage让真实Spring上下文启动并关闭任务池
2. 实现Gate.stop停止接单、有限等待、必要中断和恢复中断标记
3. 用latch控制在途任务，不用sleep猜顺序
4. 检查HealthIndicator与关闭后拒绝提交

运行本节检查：`./gradlew :06-runtime-lifecycle:test`。运行完整调用方：`./gradlew :06-runtime-lifecycle:usage`。服务型示例另可执行 `./gradlew :06-runtime-lifecycle:run`，停止使用 Ctrl+C。

## 正确性合同

上下文启动后接单；stop后拒绝新任务；stop等待上限2秒，超时调用shutdownNow；线程中断标记不能被吞。关闭后不留下本实验线程。健康UP/DOWN来自实际running状态。

## 核心机制与图解

```text
[接单中] -> [有界队列] -> [工作线程]
    |
    +-- 停止 --> [拒绝新任务] -> [shutdown] -> [限时等待]
                                                   |
                                            [超时则请求中断]
```

SmartLifecycle将资源生命周期交给真实Spring容器。先改变接单状态再shutdown，避免关闭期间持续接收任务。优雅等待有预算，超时中断也是协作信号；不响应中断的业务仍需额外保护，不能声称任何任务都能安全强杀。

## 固定版本源码阅读

[DefaultLifecycleProcessor](https://github.com/spring-projects/spring-framework/blob/6214eae8bd02c2ed7ab382bb8d16a9cc6de49522/spring-context/src/main/java/org/springframework/context/support/DefaultLifecycleProcessor.java)：onRefresh/startBeans与onClose/stopBeans；SmartLifecycle的phase与关闭顺序。

记录入口、关键分支、输入、状态与版本。不要求背整段源码；必须说明哪条观察支持你的结论。自动测试通过不等于源码讲解已通过人工评阅。

## 渐进提示

1. 先读完整调用方与测试，写出正常、边界和失败的差别
2. 只修改标出的练习区，把合同转化为分支或框架API调用
3. 对照本节真实源码入口，解释是哪一层执行校验或事务/代理行为

## 公开标准解

下面是所有练习区的完整实现；完整文件也在项目中公开。学生起点和标准解分开，不需要解锁。

```java
      ExecutorService current;
      synchronized (this) {
        if (!running) return;
        running = false;
        current = executor;
        current.shutdown();
      }
      try {
        if (!current.awaitTermination(2, TimeUnit.SECONDS)) current.shutdownNow();
      } catch (InterruptedException e) {
        current.shutdownNow();
        Thread.currentThread().interrupt();
      }
```

SmartLifecycle将资源生命周期交给真实Spring容器。先改变接单状态再shutdown，避免关闭期间持续接收任务。优雅等待有预算，超时中断也是协作信号；不响应中断的业务仍需额外保护，不能声称任何任务都能安全强杀。

## 面试机制 边界与取舍

- readiness与liveness为什么不是同一件事？一个能否接流量，一个是否需重启
- 为什么shutdown不等于任务立刻结束？已提交任务继续执行
- 中断标记为何要恢复？让上层知道当前线程被要求停止
- 关闭预算如何分配给多种资源？需要考虑依赖顺序和总预算

## 独立迁移与验收

不查标准解，修改一个合同边界并增加测试；再解释一个错误实现为什么会被拒绝。完成编码、诊断和追问才能记录掌握，阅读标准解不等于独立掌握。实际构建、集成、界面验收状态见课程根的中文阶段报告。
