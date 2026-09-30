# 12 事务代理传播与自调用失效

对应完整课程：C05-05。JDK 21，Spring Boot 3.5.16 / Framework 6.2.19。先修和运行方法见课程首页；本节全部源码、调用方、测试和标准解公开。

## 企业场景

订单服务调用审计服务；内部失败即使被catch，也可能把共享事务标记为rollback-only。另一个独立事务可能在外层回滚后保留。

## 实际操作与逐步编码

1. 实现Inner.required/independent和Outer.catchInner/failAfterAudit上的传播注解
2. 用真实DataSourceTransactionManager验证REQUIRED与REQUIRES_NEW
3. 对比withoutProxy内部自调用，定位为何没有事务
4. 在TransactionInterceptor和事务管理器打断点记录逻辑/物理事务

运行本节检查：`./gradlew :12-transaction-source:test`。运行完整调用方：`./gradlew :12-transaction-source:usage`。服务型示例另可执行 `./gradlew :12-transaction-source:run`，停止使用 Ctrl+C。

## 正确性合同

REQUIRED内部失败后外层catch仍在提交时UnexpectedRollback；REQUIRES_NEW审计在外层失败后保留；未过代理的自调用明确不启事务，本节用其作错误反例。所有SQL操作真实执行。

## 核心机制与图解

```text
[外层REQUIRED] -> [内层REQUIRED] -> [共享物理事务]
                         |失败
                         v
                   [rollback-only] -> [外层提交时报错]

[外层事务] --暂停--> [REQUIRES_NEW独立事务] --完成--> [恢复外层]
```

逻辑事务边界可以共享一个物理事务。REQUIRED的失败把共享事务标为仅回滚，外层捕获异常不会自动清除。REQUIRES_NEW暂停外层并独立提交，需要额外连接容量。自调用绕过代理，注解本身不会执行代码。

## 固定版本源码阅读

[TransactionInterceptor.invoke](https://github.com/spring-projects/spring-framework/blob/6214eae8bd02c2ed7ab382bb8d16a9cc6de49522/spring-tx/src/main/java/org/springframework/transaction/interceptor/TransactionInterceptor.java) → [TransactionAspectSupport.invokeWithinTransaction](https://github.com/spring-projects/spring-framework/blob/6214eae8bd02c2ed7ab382bb8d16a9cc6de49522/spring-tx/src/main/java/org/springframework/transaction/interceptor/TransactionAspectSupport.java) → AbstractPlatformTransactionManager提交/回滚。

记录入口、关键分支、输入、状态与版本。不要求背整段源码；必须说明哪条观察支持你的结论。自动测试通过不等于源码讲解已通过人工评阅。

## 渐进提示

1. 先读完整调用方与测试，写出正常、边界和失败的差别
2. 只修改标出的练习区，把合同转化为分支或框架API调用
3. 对照本节真实源码入口，解释是哪一层执行校验或事务/代理行为

## 公开标准解

下面是所有练习区的完整实现；完整文件也在项目中公开。学生起点和标准解分开，不需要解锁。

```java
    @Transactional(propagation = Propagation.REQUIRED)
```
```java
    @Transactional(propagation = Propagation.REQUIRES_NEW)
```
```java
    @Transactional
```
```java
    @Transactional
```

逻辑事务边界可以共享一个物理事务。REQUIRED的失败把共享事务标为仅回滚，外层捕获异常不会自动清除。REQUIRES_NEW暂停外层并独立提交，需要额外连接容量。自调用绕过代理，注解本身不会执行代码。

## 面试机制 边界与取舍

- UnexpectedRollback为什么晚于原异常？真正提交发生在外层边界
- REQUIRES_NEW为何可能耗尽连接池？外层连接可能仍占用，同时申请新连接
- checked异常默认如何回滚？默认规则与显式rollbackFor要分开验证
- 异步线程会继承当前线程事务吗？不能假定自动传播

## 独立迁移与验收

不查标准解，修改一个合同边界并增加测试；再解释一个错误实现为什么会被拒绝。完成编码、诊断和追问才能记录掌握，阅读标准解不等于独立掌握。实际构建、集成、界面验收状态见课程根的中文阶段报告。
