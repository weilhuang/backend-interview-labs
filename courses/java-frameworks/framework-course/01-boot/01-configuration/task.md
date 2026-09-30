# 01 配置绑定与启动校验

对应完整课程：C04-01。JDK 21，Spring Boot 3.5.16 / Framework 6.2.19。先修和运行方法见课程首页；本节全部源码、调用方、测试和标准解公开。

## 企业场景

订单服务允许不同环境配置最大购买数量与展示名称。配置错误应在启动时暴露，不能等用户请求时才发现。

## 实际操作与逐步编码

1. 运行Usage观察真实Spring属性绑定
2. 实现Limits.requireAllowed，保持数量区间为[1,maxQuantity]
3. 运行测试验证默认值、外部覆盖、非法配置启动失败
4. 用断点跟踪绑定器和校验器，而不是手动new替代容器

**Academy导入模式**：用本题Check检查；打开Usage.java的main运行按钮，或在Gradle工具窗口执行本模块test、usage、run。归档缺少Wrapper时不要在导入目录运行./gradlew。

**源码仓库/普通Gradle副本CLI模式**：运行本节检查：`./gradlew :01-configuration:test`。运行完整调用方：`./gradlew :01-configuration:usage`。服务型示例另可执行 `./gradlew :01-configuration:run`，停止使用 Ctrl+C。

## 正确性合同

maxQuantity配置范围为1到1000；displayName不能为空。请求数量必须为1到上限，超出抛IllegalArgumentException。启动校验和业务校验都必须存在。

## 核心机制与图解

```text
[默认值] -> [配置文件/活动配置] -> [命令行覆盖]
                                      |
                                      v
                              [绑定] -> [启动校验] -> [业务数量校验]
```

@ConfigurationProperties负责绑定，@Validated触发配置对象校验；业务方法还需校验每次请求。属性来源的覆盖不会自动修复错误数据。字段默认值与外部值通过同一路径进入最终Bean。

## 固定版本源码阅读

[Boot绑定入口](https://github.com/spring-projects/spring-boot/blob/0566f6933049aca6bc5ffc6d559fffade9cd2e0c/spring-boot-project/spring-boot/src/main/java/org/springframework/boot/context/properties/ConfigurationPropertiesBindingPostProcessor.java)：postProcessBeforeInitialization → bind。另跟踪Binder与ValidationBindHandler。

记录入口、关键分支、输入、状态与版本。不要求背整段源码；必须说明哪条观察支持你的结论。自动测试通过不等于源码讲解已通过人工评阅。

## 渐进提示

1. 先读完整调用方与测试，写出正常、边界和失败的差别
2. 只修改标出的练习区，把合同转化为分支或框架API调用
3. 对照本节真实源码入口，解释是哪一层执行校验或事务/代理行为

## 公开标准解

下面是所有练习区的完整实现；完整文件也在项目中公开。学生起点和标准解分开，不需要解锁。

```java
      if (quantity < 1 || quantity > maxQuantity) throw new IllegalArgumentException("购买数量超出配置范围");
```

@ConfigurationProperties负责绑定，@Validated触发配置对象校验；业务方法还需校验每次请求。属性来源的覆盖不会自动修复错误数据。字段默认值与外部值通过同一路径进入最终Bean。

## 面试机制 边界与取舍

- 配置绑定与@Value有什么取舍？前者适合一组可校验配置；追问：profile只是文件选择吗？
- 为什么配置校验不能代替请求校验？两者检查时机和对象不同
- 线上改配置会立即刷新Bean吗？不能假定普通Boot绑定自动动态刷新，需单独机制与安全回滚

## 独立迁移与验收

不查标准解，修改一个合同边界并增加测试；再解释一个错误实现为什么会被拒绝。完成编码、诊断和追问才能记录掌握，阅读标准解不等于独立掌握。实际构建、集成、界面验收状态见课程根的中文阶段报告。
