# 05 基础认证授权与CSRF边界

对应完整课程：C04-05。JDK 21，Spring Boot 3.5.16 / Framework 6.2.19。先修和运行方法见课程首页；本节全部源码、调用方、测试和标准解公开。

## 企业场景

内部订单接口允许阅读者查订单，管理员才能修改。即使界面隐藏修改按钮，服务端仍必须拒绝越权与无CSRF的浏览器写请求。

## 实际操作与逐步编码

1. 使用Usage查看本实验角色合同
2. 实现SecurityFilterChain：公开健康入口、阅读权限、管理员写入、默认拒绝
3. 保留CSRF保护并运行完整MockMvc安全过滤链测试
4. 比较未登录401、权限不足403、缺CSRF403与合法写入201

运行本节检查：`./gradlew :05-security:test`。运行完整调用方：`./gradlew :05-security:usage`。服务型示例另可执行 `./gradlew :05-security:run`，停止使用 Ctrl+C。

## 正确性合同

GET /public/ping公开；GET /orders需READER或ADMIN；POST /orders需ADMIN和有效CSRF；其他路径默认拒绝。仅模拟用户，不接真实身份平台。不能为了测试通过全局permitAll或禁用CSRF。

## 核心机制与图解

```text
[请求] -> [CORS] -> [CSRF] -> [认证] -> [授权] -> [控制器]
                                |         |
                             [匿名401] [越权403]
关键链路示意省略了其他过滤器；实际顺序以固定源码为准。
```

认证先建立主体，授权再匹配HTTP动作与资源。CSRF防护与角色判断解决不同风险；会话/浏览器携带凭据的写请求不能仅靠角色检查。V1只做基础安全，企业OIDC/LDAP/Keycloak在V2。

## 固定版本源码阅读

[FilterChainProxy](https://github.com/spring-projects/spring-security/blob/73b077790fcb04ac3712033d3e939daf42264545/web/src/main/java/org/springframework/security/web/FilterChainProxy.java)与[AuthorizationFilter](https://github.com/spring-projects/spring-security/blob/73b077790fcb04ac3712033d3e939daf42264545/web/src/main/java/org/springframework/security/web/access/intercept/AuthorizationFilter.java)，固定Security6.5.11。先验证来源路径再记录关键分支。

记录入口、关键分支、输入、状态与版本。不要求背整段源码；必须说明哪条观察支持你的结论。自动测试通过不等于源码讲解已通过人工评阅。

## 渐进提示

1. 先读完整调用方与测试，写出正常、边界和失败的差别
2. 只修改标出的练习区，把合同转化为分支或框架API调用
3. 对照本节真实源码入口，解释是哪一层执行校验或事务/代理行为

## 公开标准解

下面是所有练习区的完整实现；完整文件也在项目中公开。学生起点和标准解分开，不需要解锁。

```java
    return http.cors(Customizer.withDefaults())
        .authorizeHttpRequests(
            auth ->
                auth.requestMatchers("/public/ping")
                    .permitAll()
                    .requestMatchers(HttpMethod.GET, "/orders")
                    .hasAnyRole("READER", "ADMIN")
                    .requestMatchers(HttpMethod.POST, "/orders")
                    .hasRole("ADMIN")
                    .anyRequest()
                    .denyAll())
        .httpBasic(Customizer.withDefaults())
        .build();
```

认证先建立主体，授权再匹配HTTP动作与资源。CSRF防护与角色判断解决不同风险；会话/浏览器携带凭据的写请求不能仅靠角色检查。V1只做基础安全，企业OIDC/LDAP/Keycloak在V2。

## 面试机制 边界与取舍

- 401和403区别是什么？未认证与已知请求被拒绝不同
- CORS是否能阻止所有恶意调用？它是浏览器跨域机制，不能代替后端授权
- 隐藏按钮为什么不安全？客户端可以绕过页面直接发HTTP
- 何时讨论CSRF与无状态token的不同？先明确凭据如何自动附带，不盲目关闭

## 独立迁移与验收

不查标准解，修改一个合同边界并增加测试；再解释一个错误实现为什么会被拒绝。完成编码、诊断和追问才能记录掌握，阅读标准解不等于独立掌握。实际构建、集成、界面验收状态见课程根的中文阶段报告。
