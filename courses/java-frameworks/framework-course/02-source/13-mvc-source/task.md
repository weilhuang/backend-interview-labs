# 13 MVC参数解析拦截与异常处理

对应完整课程：C05-06。JDK 21，Spring Boot 3.5.16 / Framework 6.2.19。先修和运行方法见课程首页；本节全部源码、调用方、测试和标准解公开。

## 企业场景

订单接口从请求头解析教学租户上下文。明确参数解析、拦截器、控制器和异常处理的责任，同时强调真实租户身份必须来源于认证。

## 实际操作与逐步编码

1. 为Tenant实现HandlerMethodArgumentResolver
2. 通过WebMvcConfigurer注册解析器和响应轨迹拦截器
3. 在真实HTTP请求中测试合法/缺失/非法头与路径
4. 沿DispatcherServlet到参数处理器和异常解析器记录调用顺序

**Academy导入模式**：用本题Check检查；打开Usage.java的main运行按钮，或在Gradle工具窗口执行本模块test、usage、run。归档缺少Wrapper时不要在导入目录运行./gradlew。

**源码仓库/普通Gradle副本CLI模式**：运行本节检查：`./gradlew :13-mvc-source:test`。运行完整调用方：`./gradlew :13-mvc-source:usage`。服务型示例另可执行 `./gradlew :13-mvc-source:run`，停止使用 Ctrl+C。

## 正确性合同

X-Lab-Tenant匹配[a-z]{2,12}，缺失/非法400；合法返回租户与订单号；id必须正数。这个头只用于教学解析，生产必须从已认证身份绑定租户，不能信任任意用户头。

## 核心机制与图解

```text
[Servlet过滤器] -> [DispatcherServlet] -> [拦截器前置]
                                              |
                                              v
[返回值处理] <- [控制器方法] <- [参数解析与校验]
                                   |失败
                                   v
                           [异常解析器与错误响应]
```

参数解析器先用supportsParameter判断是否负责，再解析并校验。拦截器与Servlet过滤器不同；解析失败不会执行控制器业务。异常响应应稳定，不泄漏内部栈。教学头不具有授权意义。

## 固定版本源码阅读

[RequestMappingHandlerAdapter](https://github.com/spring-projects/spring-framework/blob/6214eae8bd02c2ed7ab382bb8d16a9cc6de49522/spring-webmvc/src/main/java/org/springframework/web/servlet/mvc/method/annotation/RequestMappingHandlerAdapter.java) → [InvocableHandlerMethod.getMethodArgumentValues](https://github.com/spring-projects/spring-framework/blob/6214eae8bd02c2ed7ab382bb8d16a9cc6de49522/spring-web/src/main/java/org/springframework/web/method/support/InvocableHandlerMethod.java)；异常链对照ExceptionHandlerExceptionResolver。

记录入口、关键分支、输入、状态与版本。不要求背整段源码；必须说明哪条观察支持你的结论。自动测试通过不等于源码讲解已通过人工评阅。

## 渐进提示

1. 先读完整调用方与测试，写出正常、边界和失败的差别
2. 只修改标出的练习区，把合同转化为分支或框架API调用
3. 对照本节真实源码入口，解释是哪一层执行校验或事务/代理行为

## 公开标准解

下面是所有练习区的完整实现；完整文件也在项目中公开。学生起点和标准解分开，不需要解锁。

```java
      String tenant = request.getHeader("X-Lab-Tenant");
      if (tenant == null || !tenant.matches("[a-z]{2,12}"))
        throw new IllegalArgumentException("教学租户头不合法");
      return new Tenant(tenant);
```

参数解析器先用supportsParameter判断是否负责，再解析并校验。拦截器与Servlet过滤器不同；解析失败不会执行控制器业务。异常响应应稳定，不泄漏内部栈。教学头不具有授权意义。

## 面试机制 边界与取舍

- Filter、Interceptor、AOP在哪里起作用？不同层与对象不能混为一谈
- supportsParameter为何必须精准？抢占不属于自己的参数会破坏其他解析
- 自定义参数是否自动带来安全身份？不会，信任来源要另验证
- 参数错误为什么不返回500？它属于明确的客户端输入失败

## 独立迁移与验收

不查标准解，修改一个合同边界并增加测试；再解释一个错误实现为什么会被拒绝。完成编码、诊断和追问才能记录掌握，阅读标准解不等于独立掌握。实际构建、集成、界面验收状态见课程根的中文阶段报告。
