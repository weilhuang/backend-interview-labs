# 14 自动配置条件退让与轻量Starter

对应完整课程：C05-07。JDK 21，Spring Boot 3.5.16 / Framework 6.2.19。先修和运行方法见课程首页；本节全部源码、调用方、测试和标准解公开。

## 企业场景

提供一个问候客户端的轻量starter：依赖存在且功能启用时自动装配；用户自己提供Bean时退让，不抢业务配置。

## 实际操作与逐步编码

1. 阅读真实AutoConfiguration.imports文件
2. 补上条件注解并实现从配置读取prefix
3. 检查默认启用、关闭、用户覆盖和缺依赖四种上下文
4. 读取ConditionEvaluationReport定位为什么某配置生效/未生效

运行本节检查：`./gradlew :14-autoconfiguration:test`。运行完整调用方：`./gradlew :14-autoconfiguration:usage`。服务型示例另可执行 `./gradlew :14-autoconfiguration:run`，停止使用 Ctrl+C。

## 正确性合同

默认prefix为你好，greeting.prefix可覆盖；greeting.enabled=false不装配；缺Transport类型不装配；用户自定义Greeting优先。条件不是运行时每次请求重新判断。

## 核心机制与图解

```text
[imports候选] -> [类路径条件] -> [属性条件] -> [缺Bean条件]
                                                       |
                                     +-----------------+-------------+
                                     |                               |
                                [创建默认Bean]               [保留用户自定义Bean]
```

候选导入、类路径条件、属性条件和缺Bean条件是不同阶段的筛选。@ConditionalOnMissingBean实现用户配置优先，不能靠Bean名字偶然覆盖。用ApplicationContextRunner隔离每种条件，用条件报告支持解释。

## 固定版本源码阅读

[AutoConfigurationImportSelector](https://github.com/spring-projects/spring-boot/blob/0566f6933049aca6bc5ffc6d559fffade9cd2e0c/spring-boot-project/spring-boot-autoconfigure/src/main/java/org/springframework/boot/autoconfigure/AutoConfigurationImportSelector.java)读取候选；[OnBeanCondition](https://github.com/spring-projects/spring-boot/blob/0566f6933049aca6bc5ffc6d559fffade9cd2e0c/spring-boot-project/spring-boot-autoconfigure/src/main/java/org/springframework/boot/autoconfigure/condition/OnBeanCondition.java)决定缺Bean条件。

记录入口、关键分支、输入、状态与版本。不要求背整段源码；必须说明哪条观察支持你的结论。自动测试通过不等于源码讲解已通过人工评阅。

## 渐进提示

1. 先读完整调用方与测试，写出正常、边界和失败的差别
2. 只修改标出的练习区，把合同转化为分支或框架API调用
3. 对照本节真实源码入口，解释是哪一层执行校验或事务/代理行为

## 公开标准解

下面是所有练习区的完整实现；完整文件也在项目中公开。学生起点和标准解分开，不需要解锁。

```java
  @ConditionalOnClass(name = "labs.frameworks.Transport")
  @ConditionalOnProperty(
      prefix = "greeting",
      name = "enabled",
      havingValue = "true",
      matchIfMissing = true)
```
```java
    @ConditionalOnMissingBean(Greeting.class)
```
```java
      String prefix = environment.getProperty("greeting.prefix", "你好");
      return name -> prefix + "，" + name;
```

候选导入、类路径条件、属性条件和缺Bean条件是不同阶段的筛选。@ConditionalOnMissingBean实现用户配置优先，不能靠Bean名字偶然覆盖。用ApplicationContextRunner隔离每种条件，用条件报告支持解释。

## 面试机制 边界与取舍

- 自动配置为何不是组件扫描同义词？候选元数据和条件机制不同
- 为什么用户Bean应优先？starter提供默认能力而不是强制实现
- 修改环境变量会立即重算条件吗？普通上下文不会自动刷新
- 怎样写可维护starter？小接口、清晰条件、完整组合测试、版本兼容声明

## 独立迁移与验收

不查标准解，修改一个合同边界并增加测试；再解释一个错误实现为什么会被拒绝。完成编码、诊断和追问才能记录掌握，阅读标准解不等于独立掌握。实际构建、集成、界面验收状态见课程根的中文阶段报告。
