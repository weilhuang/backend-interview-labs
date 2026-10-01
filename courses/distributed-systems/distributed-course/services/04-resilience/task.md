# 04 限流、熔断与并发隔离

对应目录 C10-04。Java 21主线，本节可独立选择Gradle模块；依赖版本、完整源码与发布状态见课程首页。所有调用方、测试、数据定义和标准解直接可见。

## 企业场景

促销流量超过库存数据库容量，下游又开始间歇失败。系统应在入口按速率拒绝、按并发限制在途任务、按依赖失败触发熔断，不能用一个大线程池同时承担三种职责。

## 概念逐层建立

- 令牌桶允许容量范围内的突发，并按时间补充；滑动日志控制任意窗口接受次数，精确但需要保存记录
- 本地额度只对一个进程有效，扩容N倍不自动保持原全局额度。分布式限流还需处理共享计数原子性、时间与故障策略
- 熔断器基于观测结果决定是否允许后续调用，不负责限制并发；半开允许少量探测以判断恢复
- bulkhead隔离在途并发，拒绝应有明确返回，异常路径必须释放许可；线程池排队会消耗deadline
- 入口限流与bulkhead拒绝不算下游失败。本课组合顺序故意把它们放在breaker之外
- 指标必须区分主动拒绝、业务失败、网络失败、熔断拒绝与超时；把所有4xx计入失败率会误伤健康服务

## ASCII机制图

```text
请求 -> 本地令牌桶 -> 并发隔离 -> 熔断器 -> 下游
          |拒绝         |拒绝      |OPEN拒绝
          v             v          v
        速率超限      在途已满    不再压垮故障依赖
                                  |
                  CLOSED -> OPEN -> HALF_OPEN
                     ^                |
                     +---探测成功-----+
```

## 实际操作与逐步编码

1. 用AtomicLong构造逻辑纳秒时钟，先耗尽容量2，再在499999999与500000000纳秒观察补充边界
2. 实现TokenBucket.allow；每次按已过时间补充且不超过capacity，同步保护复合读写
3. 实现SlidingWindow.allow，明确左开右闭窗口；用900毫秒突发说明固定窗口切换不能重置滑动日志
4. 组合真实Resilience4j breaker/bulkhead。4次受控失败打开，显式切半开触发2次成功再关闭
5. 用CountDownLatch保持2个在途请求，第3个立即拒绝，释放屏障后检查全部许可归还
6. 多线程共享一个容量7的令牌桶且时钟不走，80次尝试应恰好接受7次
7. 自己增加半开探测失败回到OPEN的断言，而不是用sleep猜测某一毫秒必须转换

以下命令用于源码仓库/公开源码包；Academy官方ZIP内用Check/Run或Gradle工具窗口执行同名任务。官方导出可能剔除Wrapper脚本/JAR，不能假设导入目录能直接运行./gradlew。独立服务课需同源shared/versions.env快照，缺失时不能视为发行完成。

本节单元检查：`./gradlew :04-resilience:test`；完整调用端：`./gradlew :04-resilience:run`。含数据库/消息服务的单元另执行 `./gradlew :04-resilience:integrationTest`，Docker不可用应明确失败，不能跳过后当作通过。每次修改先跑对应方法测试，再跑全模块回归。

## 正确性合同与保证边界

两个限流器都是明确标记的T教学模型。breaker与bulkhead使用2.3.0真实库。状态机测试显式转换半开来隔离时间，不能把它说成自动定时转换实测。库配置仍保留10秒等待策略，真实负载定时行为需独立测量。

## 固定版本源码阅读

- [resilience4j/resilience4j v2.3.0：CircuitBreakerStateMachine.java](https://github.com/resilience4j/resilience4j/blob/c2c6575114fc0650177fb21e1ff967f14acde39c/resilience4j-circuitbreaker/src/main/java/io/github/resilience4j/circuitbreaker/internal/CircuitBreakerStateMachine.java)
- [resilience4j/resilience4j v2.3.0：SemaphoreBulkhead.java](https://github.com/resilience4j/resilience4j/blob/c2c6575114fc0650177fb21e1ff967f14acde39c/resilience4j-bulkhead/src/main/java/io/github/resilience4j/bulkhead/internal/SemaphoreBulkhead.java)

阅读任务：先在本节测试找到症状，再记录入口、关键状态、分支条件和返回/清理路径。每个结论附输入、版本、符号与反例。详细入口、关键状态、分支条件和实验证据对照见课程 docs/源码路线.md。源码字节哈希与标签解析结果在课程作者验证记录中公开；没有截图不伪称做过IDE断点。

## 公开完整标准解

完整Java文件位于本节 `solutions/`，与本节标准实现逐字同步，依赖接口、调用方和测试也在本节可见。下面列出全部编码区，便于先独立完成再核对；不需要解锁或另取私有分支。

### src/labs/distributed/Lab.java 的练习实现

```java
      long now = clock.getAsLong();
      long elapsed = now - last;
      if (elapsed < 0) {
        throw new IllegalStateException("单调时钟发生倒退，检查测试时钟或运行跨度");
      }
      tokens = Math.min(capacity, tokens + elapsed * perNano);
      last = now;
      if (tokens < 1.0) {
        return false;
      }
      tokens -= 1.0;
      return true;
```
### src/labs/distributed/Lab.java 的练习实现

```java
      long now = clock.getAsLong();
      if (now < last) throw new IllegalStateException("时钟倒退");
      last = now;
      while (!accepted.isEmpty() && now - accepted.peekFirst() >= window) {
        accepted.removeFirst();
      }
      if (accepted.size() == limit) return false;
      accepted.addLast(now);
      return true;
```
### src/labs/distributed/Lab.java 的练习实现

```java
      if (!rate.allow()) throw new IllegalStateException("入口限流拒绝");
      return Bulkhead.decorateCallable(
              bulkhead, CircuitBreaker.decorateCallable(breaker, downstream))
          .call();
```

## 标准解机制、复杂度与替代取舍

TokenBucket为O(1)每次请求，使用double存小数令牌，单位为纳秒且拒绝倒退时钟；极长运行跨度/数值精度不构成金融级精确计量。滑动日志空间O(limit)，每次被接受记录仅入队/出队一次，均摊O(1)。库包装顺序确保入口拒绝没有进入breaker统计；许可在finally释放。

## 面试机制、边界与深入追问

- 问：限流、熔断和隔离可以互相替代吗？答：分别控制速率、故障后的调用策略、同时占用资源数，必须各自定义合同
- 问：半开越多探测越好？答：探测过多可能再次压垮刚恢复依赖，过少使恢复判断慢；按实例和全局探测量共同评估
- 问：本地限流10实例每秒100次是不是全局100？答：可能达到1000次，扩缩容和不均衡流量会改变实际值
- 问：滑动日志和近似滑动计数器如何选？答：日志精确但存储随额度增长，计数桶近似换取固定空间，必须说明边界误差
- 问：虚拟线程是否消除bulkhead？答：不能，数据库连接、内存与远端服务仍有容量上限
- 迁移：把入口额度按租户分配，并设计最大租户数/闲置清理，防止无限key把限流器本身撑爆

## 三阶提示与独立验收

1. 基础提示：先列正常、边界、失败后的持久状态，找到测试的业务断言，不先复制实现
2. 机制提示：把每次外部提交、响应、日志落盘、资源归还画成独立事件，检查任意相邻事件间崩溃的后果
3. 深入提示：找真正执行原子操作的数据库/框架分支，确认幂等、锁、时间与持久化前提没有被内存模型替代

独立完成一个迁移题，补失败测试，解释一份错误实现被哪条断言拒绝，再做5分钟机制答辩。看过标准答案只记录“已阅读”，不能记录“独立掌握”。实际执行通过、未执行和已知边界见课程根中文阶段报告。
