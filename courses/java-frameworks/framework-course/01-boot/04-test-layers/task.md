# 04 单元切片与真实HTTP分层测试

对应完整课程：C04-04。JDK 21，Spring Boot 3.5.16 / Framework 6.2.19。先修和运行方法见课程首页；本节全部源码、调用方、测试和标准解公开。

## 企业场景

报价服务依赖一个价格端口。业务逻辑、控制器映射和真实HTTP各有不同责任，不能用mock通过代替完整联调。

## 实际操作与逐步编码

1. 先读Unit/Slice/HTTP三层可见测试
2. 实现Quotes.total的校验、一次取价和精确乘法
3. 运行测试并指出每层能杀死哪类错误
4. 改变一个错误映射合同，同时更新对应层的测试，禁止只删断言

运行本节检查：`./gradlew :04-test-layers:test`。运行完整调用方：`./gradlew :04-test-layers:usage`。服务型示例另可执行 `./gradlew :04-test-layers:run`，停止使用 Ctrl+C。

## 正确性合同

数量范围1到100；非法数量不能调用价格端口；价格必须为正；使用精确乘法。HTTP非法输入400，下游故障503，正确报价200。所有外部依赖均是本实验显式提供的端口，无第三方访问。

## 核心机制与图解

```text
[单元]     纯对象 + 价格替身     -> 业务边界/调用次数
[切片]     MockMvc + MVC装配   -> 参数/状态码/异常映射
[集成]     真端口 + 完整Boot    -> HTTP传输/真实应用装配
```

纯单元使用Mockito检验调用次数与业务边界；MVC切片检验参数/状态码；真实随机端口检验应用装配与HTTP传输。三层测试可能有重复合同，但诊断粒度不同。mock返回值不能证明远端价格服务真的可用。

## 固定版本源码阅读

[DispatcherServlet.doDispatch](https://github.com/spring-projects/spring-framework/blob/6214eae8bd02c2ed7ab382bb8d16a9cc6de49522/spring-webmvc/src/main/java/org/springframework/web/servlet/DispatcherServlet.java)与[SpringBootTestContextBootstrapper](https://github.com/spring-projects/spring-boot/blob/0566f6933049aca6bc5ffc6d559fffade9cd2e0c/spring-boot-project/spring-boot-test/src/main/java/org/springframework/boot/test/context/SpringBootTestContextBootstrapper.java)：比较纯对象、MockMvc和真实端口的边界。

记录入口、关键分支、输入、状态与版本。不要求背整段源码；必须说明哪条观察支持你的结论。自动测试通过不等于源码讲解已通过人工评阅。

## 渐进提示

1. 先读完整调用方与测试，写出正常、边界和失败的差别
2. 只修改标出的练习区，把合同转化为分支或框架API调用
3. 对照本节真实源码入口，解释是哪一层执行校验或事务/代理行为

## 公开标准解

下面是所有练习区的完整实现；完整文件也在项目中公开。学生起点和标准解分开，不需要解锁。

```java
      if (quantity < 1 || quantity > 100) throw new IllegalArgumentException("数量不合法");
      long price = prices.unitPrice();
      if (price < 1) throw new IllegalStateException("价格服务返回错误数据");
      return Math.multiplyExact(price, quantity);
```

纯单元使用Mockito检验调用次数与业务边界；MVC切片检验参数/状态码；真实随机端口检验应用装配与HTTP传输。三层测试可能有重复合同，但诊断粒度不同。mock返回值不能证明远端价格服务真的可用。

## 面试机制 边界与取舍

- 单元与集成测试为什么都需要？速度、隔离性与真实性不同
- 什么情况下mock让你产生错误信心？真实序列化/事务/网络未执行
- 切片失败而单元通过先查什么？装配、参数转换、异常映射
- 测试数据为何要隔离？避免顺序依赖与假阳性

## 独立迁移与验收

不查标准解，修改一个合同边界并增加测试；再解释一个错误实现为什么会被拒绝。完成编码、诊断和追问才能记录掌握，阅读标准解不等于独立掌握。实际构建、集成、界面验收状态见课程根的中文阶段报告。
