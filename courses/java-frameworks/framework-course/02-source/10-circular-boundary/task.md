# 10 循环依赖的真实支持边界

对应完整课程：C05-03。JDK 21，Spring Boot 3.5.16 / Framework 6.2.19。先修和运行方法见课程首页；本节全部源码、调用方、测试和标准解公开。

## 企业场景

两个服务互相依赖导致启动失败。先用真实BeanFactory复现，再区分属性循环的早期引用与构造循环；不把放开配置当万能修复。

## 实际操作与逐步编码

1. 构造两个RootBeanDefinition，以property reference连接
2. 按参数显式设置allowCircularReferences
3. 检查允许/拒绝两种模式
4. 再运行构造注入循环，即使允许早期引用也失败
5. 提出拆职责/第三方协调者的重构方案

**Academy导入模式**：用本题Check检查；打开Usage.java的main运行按钮，或在Gradle工具窗口执行本模块test、usage、run。归档缺少Wrapper时不要在导入目录运行./gradlew。

**源码仓库/普通Gradle副本CLI模式**：运行本节检查：`./gradlew :10-circular-boundary:test`。运行完整调用方：`./gradlew :10-circular-boundary:usage`。服务型示例另可执行 `./gradlew :10-circular-boundary:run`，停止使用 Ctrl+C。

## 正确性合同

属性循环允许模式可构造并共享同一实例；拒绝模式必须失败。构造循环没有已实例化的对象可暴露，仍失败。这里直接调用BeanFactory，不把其默认值等同Boot应用默认策略。

## 核心机制与图解

```text
属性循环：  [已构造A] --设置B--> [已构造B]
                ^                 |
                +---- 设置A ------+

构造循环：  [创建A需要B] -> [创建B需要A] -> [A尚未构造，失败]
```

早期引用依赖对象已经实例化，构造阶段互相等待时没有这个条件。真实代理还可能改变早期引用的对象，因此不能背成“三级缓存解决所有循环”。本节不修改生产默认设置。

## 固定版本源码阅读

[AbstractAutowireCapableBeanFactory.doCreateBean](https://github.com/spring-projects/spring-framework/blob/6214eae8bd02c2ed7ab382bb8d16a9cc6de49522/spring-beans/src/main/java/org/springframework/beans/factory/support/AbstractAutowireCapableBeanFactory.java)：earlySingletonExposure、addSingletonFactory、getEarlyBeanReference；[DefaultSingletonBeanRegistry](https://github.com/spring-projects/spring-framework/blob/6214eae8bd02c2ed7ab382bb8d16a9cc6de49522/spring-beans/src/main/java/org/springframework/beans/factory/support/DefaultSingletonBeanRegistry.java)。

记录入口、关键分支、输入、状态与版本。不要求背整段源码；必须说明哪条观察支持你的结论。自动测试通过不等于源码讲解已通过人工评阅。

## 渐进提示

1. 先读完整调用方与测试，写出正常、边界和失败的差别
2. 只修改标出的练习区，把合同转化为分支或框架API调用
3. 对照本节真实源码入口，解释是哪一层执行校验或事务/代理行为

## 公开标准解

下面是所有练习区的完整实现；完整文件也在项目中公开。学生起点和标准解分开，不需要解锁。

```java
    var f = new DefaultListableBeanFactory();
    f.setAllowCircularReferences(allow);
    var a = new RootBeanDefinition(A.class);
    a.getPropertyValues()
        .add("b", new org.springframework.beans.factory.config.RuntimeBeanReference("b"));
    var b = new RootBeanDefinition(B.class);
    b.getPropertyValues()
        .add("a", new org.springframework.beans.factory.config.RuntimeBeanReference("a"));
    f.registerBeanDefinition("a", a);
    f.registerBeanDefinition("b", b);
    return f;
```

早期引用依赖对象已经实例化，构造阶段互相等待时没有这个条件。真实代理还可能改变早期引用的对象，因此不能背成“三级缓存解决所有循环”。本节不修改生产默认设置。

## 面试机制 边界与取舍

- 构造循环为何不同于setter循环？对象可暴露的时机不同
- 代理介入为什么更复杂？早期和最终引用的一致性要维护
- 为什么不建议靠开关修复架构？依赖方向与职责问题仍在
- @Lazy是什么取舍？延迟某次解析，不是删除真实依赖

## 独立迁移与验收

不查标准解，修改一个合同边界并增加测试；再解释一个错误实现为什么会被拒绝。完成编码、诊断和追问才能记录掌握，阅读标准解不等于独立掌握。实际构建、集成、界面验收状态见课程根的中文阶段报告。
