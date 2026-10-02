# 云原生前三课：源码Draft阶段说明

本次可保存的是Docker、Compose和容器网络前三课的源码Draft。学习材料、Java 21订单API、静态前端、答案、可见验证脚本和Academy作者元数据已经提供。JUnit桥、总课程构建和环境入口仍待接入；目前不能把这份源码包当作可直接在Academy完成Check的课程。

后续会接入唯一主课程。Kubernetes和Istio目前仅有学习设计，尚未完成可运行课程；Go静态运行镜像对照也尚未实现。

## 目录与阅读顺序

```text
cloud-native-labs/
  course/
    c11-cloud-native/          三课题目、学习者初始文件、答案说明
    materials/cloud-native/   唯一共享项目、前端、源码、图、答案和可见测试
    infra/                    待接入统一环境入口的Compose配置
  academy-overlay/
    c11-cloud-native/         section、lesson、task作者元数据与占位区
    materials/                从唯一素材源生成的预览图副本
  integration/                任务映射、运行镜像单项提案和待集成说明
  tools/                      Academy元数据生成器
```

先读[共享工程与先修词典](course/materials/cloud-native/README.md)，再依次阅读三课。网页、HTTP路由和Redis客户端均已提供；学员的重点是理解调用链、修改任务指定文件、观察业务结果。

## 三课分别学什么、做什么

| 课程 | 讲解与动手内容 | 需要观察的结果 | 答案入口 |
| --- | --- | --- | --- |
| [C11-01 Docker镜像与优雅停止](course/c11-cloud-native/01-images/01-build-and-stop/task.md) | 编译层与运行层、构建上下文、非root、PID 1和SIGTERM；补全Dockerfile并比较直接exec与exec脚本两种入口 | 运行镜像不含构建工具、源码树或合成秘密；进行中的HTTP请求完成，进程在停止预算内退出 | [逐步答案](course/c11-cloud-native/01-images/01-build-and-stop/solution.md)及[Dockerfile参考](course/materials/cloud-native/answers/Dockerfile.exec) |
| [C11-02 Compose就绪与幂等初始化](course/c11-cloud-native/02-compose/01-ready-and-seed/task.md) | 服务依赖、存活与就绪、seed和库存持久性；修复CloudPolicy并按调用顺序初始化、下单、重放和恢复依赖 | 未初始化不能接单；同一请求重放不重复扣减；重复seed不回填库存；依赖故障使业务拒绝而进程保持存活 | [逐步答案](course/c11-cloud-native/02-compose/01-ready-and-seed/solution.md)及[策略参考](course/materials/cloud-native/answers/CloudPolicy-explicit.java.txt) |
| [C11-03 容器网络与服务发现](course/c11-cloud-native/03-network/01-service-discovery/task.md) | 浏览器到API再到Redis的链路、容器内localhost、服务名与容器端口；修复AddressPolicy并阅读分层诊断 | API使用注入的redis服务名和6379容器端口；分辨DNS、CONNECT、AUTH、TIMEOUT与PROTOCOL故障 | [逐步答案](course/c11-cloud-native/03-network/01-service-discovery/solution.md)及[地址策略参考](course/materials/cloud-native/answers/AddressPolicy-explicit.java.txt) |

每课还包含结构图、逐步行动与观察提示、常见错误、面试问题和观察记录模板。上表描述的是实操验收目标；真实容器验证仍为NOT_RUN。

## 可见测试与当前能执行的检查

在本包根目录，Python离线检查入口为：

```sh
python3 course/materials/cloud-native/bin/verify_offline.py
```

[可见测试目录](course/materials/cloud-native/tests)覆盖订单库存契约、幂等初始化、就绪判断、限定项目与保卷停止、空选择和旧产物拒绝、错误解证据分类。HTTP错误解只有观察到目标业务错误并满足前后置健康条件才可接受；503依赖错误、超时或构建错误不能冒充成功反例。[Java策略断言](course/materials/cloud-native/test-java/labs/PolicyContractTest.java)是main方式的可见断言，目前尚未接成JUnit桥。

当前源码版本完成了65项Python/shell mock离线检查、10项结构检查，以及Python语法、shell语法和4处UTF-16占位范围检查。HTTP整路径回归使用模拟的HTTP传输与Docker命令，RESP假服务不执行真实Redis Lua。这些结果不证明Java或容器运行通过。

完整脚本用法与前置条件见[如何读源码和验证](course/materials/cloud-native/docs/verification.md)。

## 后续接入与未运行项目

| 项目 | 当前状态 |
| --- | --- |
| 三课section、lesson、task元数据及答案占位区 | 已提供，静态检查完成 |
| 可见JUnit桥 | 待实现 |
| 唯一主课程Gradle适配与strict dependency locks | 待实现 |
| 统一环境入口、端口预检、限定project与namespace生命周期 | 待实现 |
| Java 21编译、进程与API验证 | NOT_RUN |
| Docker镜像、真实Redis/Lua、容器网络和正负例矩阵 | NOT_RUN |
| Academy原生编辑区与Check | NOT_RUN |
| Kubernetes、Istio | 仅学习设计，可运行课程未完成 |

最终集成只取`academy-overlay/c11-cloud-native`子树，并使用`course/materials/cloud-native`唯一共享工程。`academy-overlay/materials`只用于预览，不作为第二份课程素材源。两种布局保留相同的题目图片相对链接，详见[Academy集成说明](ACADEMY-INTEGRATION.md)。镜像提案需进入唯一版本台账，不能单独当作可运行环境文件，详见[待集成依赖](integration/README.md)。
