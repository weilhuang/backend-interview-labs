# 09 Bean定义与实例生命周期

对应完整课程：C05-02。JDK 21，Spring Boot 3.5.16 / Framework 6.2.19。先修和运行方法见课程首页；本节全部源码、调用方、测试和标准解公开。

## 企业场景

平台在Bean创建前调整配置，在初始化前后记录资源状态。把修改Bean定义和处理Bean实例混在一起会产生时序问题。

## 实际操作与逐步编码

1. Usage打印真实Spring执行轨迹
2. 实现BeanFactoryPostProcessor在实例化前设置label
3. 实现BeanPostProcessor的初始化前后记录
4. 关闭上下文，验证销毁调用一次

**Academy导入模式**：用本题Check检查；打开Usage.java的main运行按钮，或在Gradle工具窗口执行本模块test、usage、run。归档缺少Wrapper时不要在导入目录运行./gradlew。

**源码仓库/普通Gradle副本CLI模式**：运行本节检查：`./gradlew :09-bean-lifecycle:test`。运行完整调用方：`./gradlew :09-bean-lifecycle:usage`。服务型示例另可执行 `./gradlew :09-bean-lifecycle:run`，停止使用 Ctrl+C。

## 正确性合同

轨迹必须是构造→属性→初始化前→初始化→初始化后→销毁；label为企业订单。后处理器只处理Account，不能对所有对象强转。不要手动调用生命周期方法造假轨迹。

## 核心机制与图解

```text
[修改Bean定义]
       |
       v
[构造] -> [属性注入] -> [初始化前处理] -> [初始化] -> [初始化后处理]
                                                              |
                                                        [关闭时销毁]
```

BeanFactoryPostProcessor处理定义，此时目标Account还未创建。BeanPostProcessor围绕初始化处理实例。关闭由Spring触发DisposableBean，不靠测试直接调用destroy。静态@Bean声明后处理器避免过早实例化配置类。

## 固定版本源码阅读

[AbstractApplicationContext.refresh](https://github.com/spring-projects/spring-framework/blob/6214eae8bd02c2ed7ab382bb8d16a9cc6de49522/spring-context/src/main/java/org/springframework/context/support/AbstractApplicationContext.java) → invokeBeanFactoryPostProcessors/registerBeanPostProcessors/finishBeanFactoryInitialization；[initializeBean](https://github.com/spring-projects/spring-framework/blob/6214eae8bd02c2ed7ab382bb8d16a9cc6de49522/spring-beans/src/main/java/org/springframework/beans/factory/support/AbstractAutowireCapableBeanFactory.java)。

记录入口、关键分支、输入、状态与版本。不要求背整段源码；必须说明哪条观察支持你的结论。自动测试通过不等于源码讲解已通过人工评阅。

## 渐进提示

1. 先读完整调用方与测试，写出正常、边界和失败的差别
2. 只修改标出的练习区，把合同转化为分支或框架API调用
3. 对照本节真实源码入口，解释是哪一层执行校验或事务/代理行为

## 公开标准解

下面是所有练习区的完整实现；完整文件也在项目中公开。学生起点和标准解分开，不需要解锁。

```java
    return factory -> factory.getBeanDefinition("account").getPropertyValues().add("label", "企业订单");
```
```java
    return new BeanPostProcessor() {
      public Object postProcessBeforeInitialization(Object bean, String name) {
        if (bean instanceof Account a) a.events.add("初始化前");
        return bean;
      }

      public Object postProcessAfterInitialization(Object bean, String name) {
        if (bean instanceof Account a) a.events.add("初始化后");
        return bean;
      }
    };
```

BeanFactoryPostProcessor处理定义，此时目标Account还未创建。BeanPostProcessor围绕初始化处理实例。关闭由Spring触发DisposableBean，不靠测试直接调用destroy。静态@Bean声明后处理器避免过早实例化配置类。

## 面试机制 边界与取舍

- 两种PostProcessor有什么不同？对象和执行阶段不同
- 为什么初始化前已经完成属性注入？要让初始化逻辑看到最终配置
- 代理常在哪个阶段加入？初始化后常见，但应以实际框架机制为准
- prototype关闭时是否和singleton一样自动销毁？不能一概而论

## 独立迁移与验收

不查标准解，修改一个合同边界并增加测试；再解释一个错误实现为什么会被拒绝。完成编码、诊断和追问才能记录掌握，阅读标准解不等于独立掌握。实际构建、集成、界面验收状态见课程根的中文阶段报告。
