# 可见原生测试桥与验证边界

`test/LabCheckTest.java` 是本题可见 JUnit 入口。统一根构建需应用
`materials/cloud-native/course.gradle`，并使用最终模块的严格依赖锁。

本题 Check 覆盖：Dockerfile与共享构建上下文的结构契约；不执行Docker或Java应用。

C11-01 的 Python 检查器只支持题面提供的两种结构：直接 exec Java 或复制共享
exec 脚本。检查器核对双阶段、统一镜像 ARG、非 root、最小 COPY、8080/TERM、
exec 入口以及共享 .dockerignore 白名单；不会构建镜像，不证明镜像层内容、PID 1
信号转发、HTTP 排空或 Redis/Lua。实际镜像与网络验收仍需共享 Docker 验证器。

C11-02/03 每题只覆盖自己的 learner Java 文件，其余共享源码从显式白名单补齐；
不编译 answers、starter、wrong 或其他题目的源文件。策略通过不证明 Compose、
Redis 幂等初始化、真实 DNS、TCP 或容器网络通过。

缺 Python/JDK、文件缺失、子进程超时、零测试及全跳过都必须失败，不能显示成功。
桥接源码和离线 Python 回归可单独验证；当前 JUnit 编译/执行、Gradle 模型、严格锁解析、
真实 Docker 以及 Academy 编辑区与 Check 交互均为 **NOT_RUN**。
