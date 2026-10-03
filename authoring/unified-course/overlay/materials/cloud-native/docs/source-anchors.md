# 官方资料与源码锚点

以下是理解本项目行为的官方阅读入口。动态文档页面不等于固定源码版本；Kubernetes与Istio尚未提供可运行实验。

## Docker、Compose与进程

- [Dockerfile规范：ENTRYPOINT、USER、COPY](https://docs.docker.com/reference/dockerfile/#entrypoint)：定位exec入口与shell父进程的区别；先跑信号实验，再读规范。练习问题：为什么JSON数组形式不自动展开`$变量`？
- [多阶段构建](https://docs.docker.com/build/building/multi-stage/)：对照本项目两个`FROM`，跟踪哪些产物从build跨到runtime。练习问题：`COPY --from=build /build /opt/app`为何过宽？
- [构建上下文与dockerignore](https://docs.docker.com/build/concepts/context/#dockerignore-files)：确认规则作用于发送给构建器的上下文。后续层删除秘密并不保证秘密未进入旧层。
- [Compose启动顺序](https://docs.docker.com/compose/how-tos/startup-order/)：对照`service_healthy`与运行期间依赖故障。练习问题：为什么依赖健康后应用仍要处理连接失败？
- [Compose网络](https://docs.docker.com/compose/how-tos/networking/)：定位服务名、动态IP及host/container端口区别。练习问题：容器更新后应保留名字还是IP？
- [Compose stop](https://docs.docker.com/reference/cli/docker/compose/stop/)：本课程停止保留数据，不使用全局清理。

## Java 21与Redis

- [JDK21 HttpServer.stop(int)](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpServer.html#stop(int))：对照`CloudNativeApp.stop()`的3秒请求等待预算和Docker的6秒总预算。预算必须能在测试中观察，不只写在注释里。
- [JDK21 Runtime.addShutdownHook](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Runtime.html#addShutdownHook(java.lang.Thread))：解释为什么必须让TERM到达JVM；强制kill不应假设hook执行。
- [Redis EVAL](https://redis.io/docs/latest/commands/eval/)：`Inventory.RESERVE`把key放KEYS、数据放ARGV。不要在脚本里偷偷生成跨槽键。
- [Redis Lua原子执行](https://redis.io/docs/latest/develop/programmability/eval-intro/)：本课一次库存检查/扣减/记录在一个脚本里；长时间脚本会影响Redis处理其他工作，因此脚本必须小而有界。
- [Redis持久化](https://redis.io/docs/latest/operate/oss_and_stack/management/persistence/)：本课验证正常停止重启的保留性，不外推断电零丢失或灾备能力。

## 运行镜像固定源码

运行层使用一个JRE key `JAVA_RUNTIME_IMAGE`，值由唯一版本台账管理，课文不再复制镜像常量。

- [官方Temurin当前21版本](https://adoptium.net/temurin/releases?version=21)
- [Docker官方镜像声明](https://github.com/docker-library/official-images/blob/master/library/eclipse-temurin)
- [JRE镜像对应的固定源码commit](https://github.com/adoptium/containers/tree/511f9356dc4d50932a0a5f8cfb0f87ed1aef4f07/21/jre/ubuntu/jammy)

运行镜像应由总课程唯一版本台账固定，包含准确版本与digest。本草稿未拉取或运行镜像，也未进行双架构实机验证；不能仅凭版本选择宣称测试通过。
