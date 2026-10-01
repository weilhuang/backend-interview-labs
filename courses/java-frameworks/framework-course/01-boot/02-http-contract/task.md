# 02 HTTP校验错误与预置前端

对应完整课程：C04-02。JDK 21，Spring Boot 3.5.16 / Framework 6.2.19。先修和运行方法见课程首页；本节全部源码、调用方、测试和标准解公开。

## 企业场景

用户在中文订单页提交SKU、数量、单价与请求编号。网络重试不能重复创建订单；相同编号不同内容必须明确冲突。

## 实际操作与逐步编码

1. 执行run并打开http://127.0.0.1:18084
2. 先通过页面和Usage调用成功/非法请求
3. 实现Store.create中的原子幂等决策、金额溢出检查与ID分配
4. 运行真实随机端口HTTP测试，检查201/200/400/404/409与Location
5. 在页面尝试重复点击、相同键改参数、非法数量和刷新列表

**Academy导入模式**：用本题Check检查；打开Usage.java的main运行按钮，或在Gradle工具窗口执行本模块test、usage、run。归档缺少Wrapper时不要在导入目录运行./gradlew。

**源码仓库/普通Gradle副本CLI模式**：运行本节检查：`./gradlew :02-http-contract:test`。运行完整调用方：`./gradlew :02-http-contract:usage`。服务型示例另可执行 `./gradlew :02-http-contract:run`，停止使用 Ctrl+C。

## 正确性合同

字段不得空白，数量与单价为正；最大数量100。金额用Math.multiplyExact。新建201、同键同内容200且同ID、同键不同内容409、非法请求400、不存在404。列表按ID升序，offset>=0、limit为1到100，默认前20条；请求失败不得新增记录。教学内存存储仅单进程，重启丢失。

## 核心机制与图解

```text
[中文页面/调用方] -> [JSON解析与校验] -> [请求编号查重]
                                              |
                          +-------------------+------------------+
                          |                   |                  |
                       [新建201]          [同内容200]        [冲突409]
```

@Valid负责结构约束，Store负责动态数量上限、幂等与溢出。synchronized使同进程的查重和写入成为一个临界区；生产多实例需数据库唯一约束等持久机制。@RestControllerAdvice把预期错误转为稳定响应，不向调用方泄漏堆栈。

## 固定版本源码阅读

[MVC入口](https://github.com/spring-projects/spring-framework/blob/6214eae8bd02c2ed7ab382bb8d16a9cc6de49522/spring-webmvc/src/main/java/org/springframework/web/servlet/DispatcherServlet.java)：doDispatch。参数解析经RequestResponseBodyMethodProcessor；异常经ExceptionHandlerExceptionResolver。

记录入口、关键分支、输入、状态与版本。不要求背整段源码；必须说明哪条观察支持你的结论。自动测试通过不等于源码讲解已通过人工评阅。

## 渐进提示

1. 先读完整调用方与测试，写出正常、边界和失败的差别
2. 只修改标出的练习区，把合同转化为分支或框架API调用
3. 对照本节真实源码入口，解释是哪一层执行校验或事务/代理行为

## 公开标准解

下面是所有练习区的完整实现；完整文件也在项目中公开。学生起点和标准解分开，不需要解锁。

```java
      if (r.quantity() < 1 || r.quantity() > 100 || r.unitPriceFen() < 1)
        throw new IllegalArgumentException("数量或金额不合法");
      long total = Math.multiplyExact(r.quantity(), r.unitPriceFen());
      Order old = requests.get(r.requestId());
      if (old != null) {
        if (!old.sku().equals(r.sku())
            || old.quantity() != r.quantity()
            || old.unitPriceFen() != r.unitPriceFen()) throw new Conflict();
        return new Creation(old, false);
      }
      Order order =
          new Order(++sequence, r.requestId(), r.sku(), r.quantity(), r.unitPriceFen(), total);
      requests.put(r.requestId(), order);
      return new Creation(order, true);
```

@Valid负责结构约束，Store负责动态数量上限、幂等与溢出。synchronized使同进程的查重和写入成为一个临界区；生产多实例需数据库唯一约束等持久机制。@RestControllerAdvice把预期错误转为稳定响应，不向调用方泄漏堆栈。

## 面试机制 边界与取舍

- POST可以设计成业务幂等吗？可以，但需要明确键作用域/有效期/持久化；追问：服务重启后的保证是什么？
- 为什么校验注解不放在前端就结束？客户端可绕过，后端仍负责合同
- 重复请求返回200还是201？由合同定义，本课区别已存在和新建
- 为什么不用double计算钱？精确单位和溢出合同必须明确

## 独立迁移与验收

不查标准解，修改一个合同边界并增加测试；再解释一个错误实现为什么会被拒绝。完成编码、诊断和追问才能记录掌握，阅读标准解不等于独立掌握。实际构建、集成、界面验收状态见课程根的中文阶段报告。
