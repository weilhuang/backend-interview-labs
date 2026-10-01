# 02 gRPC真实网络、截止与流控

对应目录 C10-02。Java 21主线，本节可独立选择Gradle模块；依赖版本、完整源码与发布状态见课程首页。所有调用方、测试、数据定义和标准解直接可见。

## 企业场景

订单网关调用库存服务，同时服务端向慢消费者推送库存快照。一次调用可能经过两跳，前端总预算不能在每跳重新计算。消费者只处理一条时，服务端不能无限制在应用层积累数据。

## 概念逐层建立

- proto字段编号是线协议契约。增添可选含义字段通常比复用已删除字段安全；保留字段编号，测试未知字段往返
- unary与server-streaming有不同生命周期；gRPC状态码在调用边界表达INVALID_ARGUMENT、FAILED_PRECONDITION、UNAVAILABLE、RESOURCE_EXHAUSTED
- stub上的deadline限制等待；Context携带截止和取消通知，业务自己启动的线程、数据库事务仍需独立关闭/超时
- 拦截器传递经过长度/字符集校验的追踪标识。它不是认证凭据，不能当作租户身份
- HTTP/2流控只控制数据流量，不等于业务请求准入。`isReady`表示框架可继续接受写入，不保证消息已交付消费者
- 本机测试用真实Netty TCP，明确关闭in-process捷径；明文只限127.0.0.1实验。生产需要证书、服务身份与授权

## ASCII机制图

```text
客户端[总预算4秒]
   | gRPC HTTP/2 + trace-id + deadline
   v
网关 Context[剩余<4秒]
   | 显式下游上限8秒，但有效值=min(上下文剩余,8秒)
   v
库存服务 -> 响应剩余预算、追踪标识

订阅者 request(1) -> 框架流控 -> onNext一次
                  cancel -> 服务端onCancel清理
```

## 实际操作与逐步编码

1. 读 `proto/inventory.proto` 和完整生成文件。运行 `:02-grpc:run` 确认打印随机TCP端口、库存、追踪和剩余预算
2. 编写 `TraceInterceptor.interceptCall`，用参数合法/非法/缺失测试验证，不用ThreadLocal保存请求身份
3. 编写 `Service.reserve` 参数检查：有效幂等键、数量1到1000；运行真实网络参数测试
4. 在两跳测试中观察下游剩余时间不超过上游；把下游上限设大也不能突破Context截止
5. 触发wait故障分支，在截止后确认activeWaits归零。区分客户端收到错误与服务端清理完成两个断言
6. 实现watch的isReady/onCancel循环，使用手动request(1)证明应用只收到一条，然后取消
7. 增加未知字段99，旧消息读出再写回仍保留未知字段；不要把兼容测试写成字符串比较

以下命令用于源码仓库/公开源码包；Academy官方ZIP内用Check/Run或Gradle工具窗口执行同名任务。官方导出可能剔除Wrapper脚本/JAR，不能假设导入目录能直接运行./gradlew。独立服务课需同源shared/versions.env快照，缺失时不能视为发行完成。

本节单元检查：`./gradlew :02-grpc:test`；完整调用端：`./gradlew :02-grpc:run`。含数据库/消息服务的单元另执行 `./gradlew :02-grpc:integrationTest`，Docker不可用应明确失败，不能跳过后当作通过。每次修改先跑对应方法测试，再跑全模块回归。

## 正确性合同与保证边界

默认没有写操作自动重试，channel.disableRetry。示例Backend只是可替换业务接口，网络单元中的固定库存不是持久化实现；C10-08注入真实MySQL幂等存储。订阅最多128条，消息大小受1MiB入口限制，生成载荷用于观察流控。截止不承诺中止已提交SQL。

## 固定版本源码阅读

- [grpc/grpc-java v1.71.0：ClientCallImpl.java](https://github.com/grpc/grpc-java/blob/865c4432569dfdf738b3cf07bcdb6d6e3285f761/core/src/main/java/io/grpc/internal/ClientCallImpl.java)
- [grpc/grpc-java v1.71.0：RetriableStream.java](https://github.com/grpc/grpc-java/blob/865c4432569dfdf738b3cf07bcdb6d6e3285f761/core/src/main/java/io/grpc/internal/RetriableStream.java)
- [grpc/grpc-java v1.71.0：ClientCalls.java](https://github.com/grpc/grpc-java/blob/865c4432569dfdf738b3cf07bcdb6d6e3285f761/stub/src/main/java/io/grpc/stub/ClientCalls.java)
- [grpc/grpc-java v1.71.0：ServerCalls.java](https://github.com/grpc/grpc-java/blob/865c4432569dfdf738b3cf07bcdb6d6e3285f761/stub/src/main/java/io/grpc/stub/ServerCalls.java)

阅读任务：先在本节测试找到症状，再记录入口、关键状态、分支条件和返回/清理路径。每个结论附输入、版本、符号与反例。详细入口、关键状态、分支条件和实验证据对照见课程 docs/源码路线.md。源码字节哈希与标签解析结果在课程作者验证记录中公开；没有截图不伪称做过IDE断点。

## 公开完整标准解

完整Java文件位于本节 `solutions/`，与本节标准实现逐字同步，依赖接口、调用方和测试也在本节可见。下面列出全部编码区，便于先独立完成再核对；不需要解锁或另取私有分支。

### src/labs/distributed/grpc/Lab.java 的练习实现

```java
      String trace = headers.get(TRACE_HEADER);
      if (trace == null || !trace.matches("[a-zA-Z0-9_-]{1,64}")) {
        call.close(Status.INVALID_ARGUMENT.withDescription("追踪标识缺失或非法"), new Metadata());
        return new ServerCall.Listener<>() {};
      }
      return Contexts.interceptCall(
          Context.current().withValue(TRACE_CONTEXT, trace), call, headers, next);
```
### src/labs/distributed/grpc/Lab.java 的练习实现

```java
      if (request.getKey().isBlank()
          || request.getKey().length() > 64
          || request.getSku().isBlank()
          || request.getQuantity() < 1
          || request.getQuantity() > 1000) {
        observer.onError(
            Status.INVALID_ARGUMENT.withDescription("幂等键、商品和数量必须合法").asRuntimeException());
        return;
      }
      respond(
          observer,
          request.getSku(),
          () -> backend.reserve(request.getKey(), request.getSku(), request.getQuantity()));
```
### src/labs/distributed/grpc/Lab.java 的练习实现

```java
            while (output.isReady() && !output.isCancelled() && sent.get() < request.getCount()) {
              int index = sent.incrementAndGet();
              output.onNext(
                  reply("商品-" + index, index).toBuilder().setPayload("数".repeat(16_384)).build());
              emitted.incrementAndGet();
            }
            if (sent.get() == request.getCount() && !output.isCancelled()) output.onCompleted();
```

## 标准解机制、复杂度与替代取舍

拦截器在业务执行前建立Context；自动跨跳deadline取较短者。取消监听器只释放明确拥有的挂起资源；不要在RPC关闭时回滚另一事务。流控写入在回调中检查isReady，最多生成128条，空间主要由框架有界写缓冲和单消息大小决定。`client`保留deadline与metadata，所有Endpoint关闭channel和server并等待退出。

## 面试机制、边界与深入追问

- 问：deadline和timeout有什么不同？答：deadline约束整体完成时点，每跳消耗剩余预算；多个独立timeout容易累计超时。边界：跨主机不直接比较System.nanoTime
- 问：DEADLINE_EXCEEDED之后库存一定没变？答：不一定，业务提交和响应存在窗口，写入必须带可查询的幂等键
- 问：onNext返回就是发送完成吗？答：不是，可能仅排入框架缓冲。追问：应用忽略isReady会怎样？可能放大内存和取消后浪费
- 问：为什么追踪标识不是用户身份？答：它由调用方可控，只关联日志；鉴权需要可信签名/令牌及服务端授权
- 问：修改proto字段类型有什么风险？答：编号与wire type/语义都参与兼容；旧端可能静默误读，需保留编号并设计迁移
- 迁移：新增只读批量库存查询，保留总预算和消息上限，测试空列表、超过上限与消费者提前取消

## 三阶提示与独立验收

1. 基础提示：先列正常、边界、失败后的持久状态，找到测试的业务断言，不先复制实现
2. 机制提示：把每次外部提交、响应、日志落盘、资源归还画成独立事件，检查任意相邻事件间崩溃的后果
3. 深入提示：找真正执行原子操作的数据库/框架分支，确认幂等、锁、时间与持久化前提没有被内存模型替代

独立完成一个迁移题，补失败测试，解释一份错误实现被哪条断言拒绝，再做5分钟机制答辩。看过标准答案只记录“已阅读”，不能记录“独立掌握”。实际执行通过、未执行和已知边界见课程根中文阶段报告。
