# 08 最小容器与真实构造注入

对应完整课程：C05-01。JDK 21，Spring Boot 3.5.16 / Framework 6.2.19。先修和运行方法见课程首页；本节全部源码、调用方、测试和标准解公开。

## 企业场景

理解Spring之前先明确容器解决什么：依赖构造、共享实例与错误报告。教学容器只支持公开单构造器，不冒充Spring。

## 实际操作与逐步编码

1. 运行Usage查看真实Spring注入
2. 实现Tiny.get的构造递归、单例缓存和循环路径清理
3. 对照真实AnnotationConfigApplicationContext的Bean创建
4. 用缺失构造器/循环依赖反例解释模型省略了什么

**Academy导入模式**：用本题Check检查；打开Usage.java的main运行按钮，或在Gradle工具窗口执行本模块test、usage、run。归档缺少Wrapper时不要在导入目录运行./gradlew。

**源码仓库/普通Gradle副本CLI模式**：运行本节检查：`./gradlew :08-container-di:test`。运行完整调用方：`./gradlew :08-container-di:usage`。服务型示例另可执行 `./gradlew :08-container-di:run`，停止使用 Ctrl+C。

## 正确性合同

Tiny只支持恰好一个公开构造器、无基本类型参数的类；每类型同一实例；循环依赖明确失败；失败不得污染正在构造集合。没有scope、代理、属性注入、生命周期、注解扫描。

## 核心机制与图解

```text
[按类型获取] -> [缓存命中?] --是--> [同一实例]
                    |否
                    v
              [构造路径检查] -> [递归解析依赖] -> [创建并缓存]
                    |
                 [循环报错]
```

缓存命中和正在构造是不同状态。先标记构造中、递归解决依赖、成功后缓存，并在finally清理标记。真实Spring的BeanDefinition、scope、工厂Bean、后处理和早期引用远比模型复杂。

## 固定版本源码阅读

[AbstractBeanFactory.doGetBean](https://github.com/spring-projects/spring-framework/blob/6214eae8bd02c2ed7ab382bb8d16a9cc6de49522/spring-beans/src/main/java/org/springframework/beans/factory/support/AbstractBeanFactory.java) → [AbstractAutowireCapableBeanFactory.createBean](https://github.com/spring-projects/spring-framework/blob/6214eae8bd02c2ed7ab382bb8d16a9cc6de49522/spring-beans/src/main/java/org/springframework/beans/factory/support/AbstractAutowireCapableBeanFactory.java)。比较真实缓存、依赖解析和教学模型。

记录入口、关键分支、输入、状态与版本。不要求背整段源码；必须说明哪条观察支持你的结论。自动测试通过不等于源码讲解已通过人工评阅。

## 渐进提示

1. 先读完整调用方与测试，写出正常、边界和失败的差别
2. 只修改标出的练习区，把合同转化为分支或框架API调用
3. 对照本节真实源码入口，解释是哪一层执行校验或事务/代理行为

## 公开标准解

下面是所有练习区的完整实现；完整文件也在项目中公开。学生起点和标准解分开，不需要解锁。

```java
      if (cache.containsKey(type)) return type.cast(cache.get(type));
      if (!constructing.add(type)) throw new IllegalStateException("检测到构造循环：" + type.getName());
      try {
        var constructors = type.getConstructors();
        if (constructors.length != 1) throw new IllegalArgumentException("教学容器只支持一个公开构造器");
        var constructor = constructors[0];
        Object[] args = Arrays.stream(constructor.getParameterTypes()).map(this::get).toArray();
        T result = type.cast(constructor.newInstance(args));
        cache.put(type, result);
        return result;
      } catch (ReflectiveOperationException e) {
        throw new IllegalStateException("构造失败", e);
      } finally {
        constructing.remove(type);
      }
```

缓存命中和正在构造是不同状态。先标记构造中、递归解决依赖、成功后缓存，并在finally清理标记。真实Spring的BeanDefinition、scope、工厂Bean、后处理和早期引用远比模型复杂。

## 面试机制 边界与取舍

- IoC与DI是什么关系？控制创建和协作关系，注入是实现方式
- 单例Bean是否自动线程安全？生命周期共享不等于状态同步
- 为什么失败后要清理构造标记？否则后续合法请求会被误判
- 为什么生产代码不直接用这个Tiny？功能与诊断边界故意缩小

## 独立迁移与验收

不查标准解，修改一个合同边界并增加测试；再解释一个错误实现为什么会被拒绝。完成编码、诊断和追问才能记录掌握，阅读标准解不等于独立掌握。实际构建、集成、界面验收状态见课程根的中文阶段报告。
