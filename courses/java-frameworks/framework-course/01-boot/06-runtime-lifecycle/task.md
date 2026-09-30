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

上下文启动后接单；stop后拒绝新任务。关闭总等待预算2秒，其中正常完成最多1.5秒；超时或调用线程中断后执行shutdownNow，并将移出队列的Future显式取消，不能留下永远未完成的Future。余下预算等待工作线程退出；不响应中断而耗尽预算时明确报错，不能冒充安全强杀。退出时恢复调用线程中断标记。健康UP/DOWN来自实际running状态。

## 核心机制与图解

```text
[接单中] -> [有界队列] -> [工作线程]
    |
    +-- 停止 --> [拒绝新任务] -> [shutdown] -> [限时等待]
                                                   |
                                            [超时/中断 -> 取消排队Future -> 有界等退出]
```

SmartLifecycle把资源生命周期交给真实Spring容器。先停止接单，再允许有界正常完成；shutdownNow只发中断并返回尚未执行的Runnable，它不会自动把这些FutureTask标为已取消。因此必须显式cancel移出队列的Future，并在同一总预算内等待工作线程结束。调用方被中断时也必须完成有界清理，最后恢复中断标记。业务不响应中断时只能明确报告关闭失败，不能声称任何任务都能安全强杀。

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
      // 总预算2秒：先给正常完成1.5秒，再为中断后的资源清理预留时间。
      long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(2);
      boolean interrupted = false;
      try {
        boolean complete = false;
        try {
          complete = current.awaitTermination(1500, TimeUnit.MILLISECONDS);
        } catch (InterruptedException e) {
          interrupted = true;
        }
        if (!complete) {
          // shutdownNow只移出等待队列，不会替调用方取消那些Future。
          for (Runnable task : current.shutdownNow()) {
            if (task instanceof Future<?> future) future.cancel(false);
          }
          while (!current.isTerminated()) {
            long remaining = deadline - System.nanoTime();
            if (remaining <= 0) throw new IllegalStateException("任务未响应取消，关闭预算已耗尽");
            try {
              if (current.awaitTermination(remaining, TimeUnit.NANOSECONDS)) break;
            } catch (InterruptedException e) {
              // 清理仍受同一总预算约束；退出时再恢复调用线程的中断信号。
              interrupted = true;
            }
          }
        }
      } finally {
        if (interrupted) Thread.currentThread().interrupt();
      }
```

SmartLifecycle把资源生命周期交给真实Spring容器。先停止接单，再允许有界正常完成；shutdownNow只发中断并返回尚未执行的Runnable，它不会自动把这些FutureTask标为已取消。因此必须显式cancel移出队列的Future，并在同一总预算内等待工作线程结束。调用方被中断时也必须完成有界清理，最后恢复中断标记。业务不响应中断时只能明确报告关闭失败，不能声称任何任务都能安全强杀。

## 面试机制 边界与取舍

- readiness与liveness为什么不是同一件事？一个能否接流量，一个是否需重启
- 为什么shutdown不等于任务立刻结束？已提交任务继续执行
- 中断标记为何要恢复？让上层知道当前线程被要求停止
- 关闭预算如何分配给多种资源？需要考虑依赖顺序和总预算

## 独立迁移与验收

不查标准解，修改一个合同边界并增加测试；再解释一个错误实现为什么会被拒绝。完成编码、诊断和追问才能记录掌握，阅读标准解不等于独立掌握。实际构建、集成、界面验收状态见课程根的中文阶段报告。
