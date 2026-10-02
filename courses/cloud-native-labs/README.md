# 云原生前三课：源码草稿

本包包含Docker镜像、Compose生命周期和容器网络三课。课程用已提供的Java 21订单API、静态前端和Redis库存贯穿学习过程，不要求你先会前端框架、Kubernetes或Istio。

## 内容入口

- `course/materials/cloud-native/README.md`：先修词典、项目结构和API契约
- `course/c11-cloud-native/01-images/01-build-and-stop`：镜像边界、非root、TERM排空
- `course/c11-cloud-native/02-compose/01-ready-and-seed`：就绪、幂等初始化和故障恢复
- `course/c11-cloud-native/03-network/01-service-discovery`：容器DNS、端口和分层诊断
- `course/materials/cloud-native/tests`：可见业务断言、正确/错误变体检查和离线回归
- `course/materials/cloud-native/answers`：标准答案与另一种正确写法
- `course/infra/cloudnative.compose.yaml`：待总课程环境入口集成的编排配置
- `academy-overlay`：三课的Academy作者元数据和答案区，仅供后续集成

## 当前边界

这是前三课源码草稿，不是完整云原生课程。当前Java编译/运行、Docker与真实Redis/Lua、Academy原生Check均为NOT_RUN。离线检查的当前结果单独记录，不沿用以前的运行结果。

总课程的JUnit桥、Gradle适配与strict dependency locks尚未提供；不能把存在task-info.yaml等同于Check已经可用。Kubernetes、Istio仅有学习设计，Go静态镜像对照仍未实现。

完整验证方式和安全边界见 `course/materials/cloud-native/docs/verification.md`。
