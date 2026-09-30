# 11 真实代理拦截链与自调用

对应完整课程：C05-04。JDK 21，Spring Boot 3.5.16 / Framework 6.2.19。先修和运行方法见课程首页；本节全部源码、调用方、测试和标准解公开。

## 企业场景

支付演示服务通过代理统一验证参数并记录调用。内部this调用绕过代理时，为什么看起来同一个方法行为不同？

## 实际操作与逐步编码

1. 用ProxyFactory分别创建JDK代理和类代理
2. 实现拦截器的前置校验、proceed、finally记录
3. 对比外部charge与内部batch调用
4. 异常传播不能吞掉，解释拆分服务注入代理的修复方法

运行本节检查：`./gradlew :11-aop-proxy:test`。运行完整调用方：`./gradlew :11-aop-proxy:usage`。服务型示例另可执行 `./gradlew :11-aop-proxy:run`，停止使用 Ctrl+C。

## 正确性合同

外部charge金额必须正数；拦截轨迹包括进入/退出，异常也退出。方法返回值和原异常保持。batch内部直接调用charge用于展示自调用绕过，不得把该演示当生产支付代码。

## 核心机制与图解

```text
外部调用： [客户端] -> [代理] -> [拦截器] -> [目标charge]
自调用：   [客户端] -> [代理] -> [目标batch] -> [this.charge]
                                                 |
                                          [不重新经过代理]
```

代理包装的是外部调用入口，target对象内部的this仍是target。拦截器必须调用proceed才能继续到目标，finally让失败也能记录退出。校验时机、异常与返回值都是合同，不只检查是否打印日志。

## 固定版本源码阅读

[JdkDynamicAopProxy.invoke](https://github.com/spring-projects/spring-framework/blob/6214eae8bd02c2ed7ab382bb8d16a9cc6de49522/spring-aop/src/main/java/org/springframework/aop/framework/JdkDynamicAopProxy.java) → [ReflectiveMethodInvocation.proceed](https://github.com/spring-projects/spring-framework/blob/6214eae8bd02c2ed7ab382bb8d16a9cc6de49522/spring-aop/src/main/java/org/springframework/aop/framework/ReflectiveMethodInvocation.java)。类代理对照CglibAopProxy。

记录入口、关键分支、输入、状态与版本。不要求背整段源码；必须说明哪条观察支持你的结论。自动测试通过不等于源码讲解已通过人工评阅。

## 渐进提示

1. 先读完整调用方与测试，写出正常、边界和失败的差别
2. 只修改标出的练习区，把合同转化为分支或框架API调用
3. 对照本节真实源码入口，解释是哪一层执行校验或事务/代理行为

## 公开标准解

下面是所有练习区的完整实现；完整文件也在项目中公开。学生起点和标准解分开，不需要解锁。

```java
    ProxyFactory factory = new ProxyFactory(new PaymentService());
    factory.setProxyTargetClass(classProxy);
    factory.addAdvice(
        (MethodInterceptor)
            invocation -> {
              if (invocation.getMethod().getName().equals("charge")
                  && (int) invocation.getArguments()[0] < 1)
                throw new IllegalArgumentException("金额必须为正");
              events.add("进入:" + invocation.getMethod().getName());
              try {
                return invocation.proceed();
              } finally {
                events.add("退出:" + invocation.getMethod().getName());
              }
            });
    return (Payments) factory.getProxy();
```

代理包装的是外部调用入口，target对象内部的this仍是target。拦截器必须调用proceed才能继续到目标，finally让失败也能记录退出。校验时机、异常与返回值都是合同，不只检查是否打印日志。

## 面试机制 边界与取舍

- JDK代理与类代理有什么边界？接口与可覆盖方法的限制不同
- 为什么self-invocation不重新过代理？接收者是target本身
- final方法可被类代理覆盖吗？不能按普通可覆盖方法处理
- AOP为什么不能代替领域校验？调用入口可能绕过代理，关键规则要在合适层保护

## 独立迁移与验收

不查标准解，修改一个合同边界并增加测试；再解释一个错误实现为什么会被拒绝。完成编码、诊断和追问才能记录掌握，阅读标准解不等于独立掌握。实际构建、集成、界面验收状态见课程根的中文阶段报告。
