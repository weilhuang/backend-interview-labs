# 每门后端课程的运行契约

本文件规定后续项目课如何接入共享基础环境，不代表 Spring、消息队列或前端项目已经交付。当前 Java 集合首包没有 Web 页面，也不需要为其伪造一个通用前端。

## 1. 面向学习者的边界

课程涉及 Web/接口调试时，由课程作者提供已构建、已集成的可用前端。学习者打开页面即可验证业务，不需要另建 Vue/React 工程、安装 Node、处理代理/CORS、补接口地址或手接中间件。页面必须服务于该课的真实实验，例如订单创建、重复请求、缓存命中、消息状态或链路追踪入口，不能用“能打开的空壳”算完成。

每课发布物需列出：

1. JDK **21**、IDEA/Academy 的最低依赖、**实际测试版本**、构建 Wrapper/BOM、共享基础设施组件组
2. 后端与前端构建版本、前端静态产物路径/校验值、后端接口兼容版本
3. 复制即可执行的启动命令，以及后端就绪、页面访问、业务验证命令
4. 宿主与容器两套明确配置；共享镜像版本以 `infra/versions.env` 为唯一依据
5. 默认端口、资源/磁盘预算、初始化数据、重置范围、已知限制

## 2. 推荐交付结构与健康检查

```text
课程发布物（未来项目课）
+-- README.md             前置表 + 一键启动 + 验收
+-- 后端项目/             JDK 21 + 锁定 Wrapper/BOM
+-- 预置静态前端产物/      作者构建与集成，学习者免 Node
+-- 应用配置/             host/container 两种地址，非生产凭据
+-- smoke/                页面 + 接口 + 真实业务读写验证
          |
          +-- 共享 infra/versions.env
          +-- 共享 MySQL/Redis/Kafka（仅启动所需组）
```

优先把预置静态资源打入 Spring Boot 包，前后端同源；其他方式必须同样做到启动后直接可用。具体路由、健康端点和业务字段由真实课程实现确定，不在这里假定所有技术栈共用同一套 API。

后端容器不能因数据库“进程存在”就宣布就绪。先通过基础服务协议检查，再通过后端 readiness，再验证前端页面与完整业务链。前端构建通过不等于 UI 可用；至少覆盖初始加载、成功提交、接口错误、重复操作、刷新/返回和数据持久化。

## 3. Compose 与 Testcontainers 复用镜像，不共享测试数据

- `infra/compose.yaml` 用 `${MYSQL_IMAGE}` 等变量读取同一个台账
- 后续课程把 [`infra/testcontainers/LabImages.java`](../../infra/testcontainers/LabImages.java) 加入**测试源码集**，不复制文件内容或硬编码标签
- `LabImages.image("MYSQL_IMAGE")`、`LabImages.image("REDIS_IMAGE")`、`LabImages.image("KAFKA_IMAGE")` 返回与 Compose 完全相同的引用，交给课程锁定版 Testcontainers 的 `DockerImageName.parse(...)`
- 读取器从当前课程目录向上查找仓库台账；找不到就失败。脱离仓库单独导出的课程需由发布流程附带同一份台账及来源校验，不能静默使用备用版本
- 各课固定 Testcontainers BOM/版本，不用动态依赖；首次真正接入时按该版本补充辅助镜像（Ryuk 等）清单与验证，不把业务镜像表误称为零额外下载保证
- Testcontainers 使用临时容器、独立数据库和随机宿主端口，通过 `getHost()`、`getMappedPort(...)` 获取连接信息；不复用 Compose 的教学数据卷，也不抢占固定实验端口
- 不为节省磁盘关闭资源清理器、健康检查或默认启用实验性的容器复用；共享的是镜像层，测试隔离仍然保留

示例表达式（不是已运行的集成测试）：

```java
DockerImageName mysqlImage = DockerImageName.parse(LabImages.image("MYSQL_IMAGE"));
DockerImageName redisImage = DockerImageName.parse(LabImages.image("REDIS_IMAGE"));
DockerImageName kafkaImage = DockerImageName.parse(LabImages.image("KAFKA_IMAGE"));
```

Testcontainers 的模块、包名和构造函数以该课实际锁定版本为准。Kafka 应选与 `apache/kafka` 兼容的模块，不能把 Confluent 模块的默认镜像替换后就声称兼容。

当前 Java 基础题不依赖 Testcontainers；这里交付的是共享读取器和接入规范，不是不存在的数据库/消息队列课程测试报告。

## 4. 发布前必须完成的实机验收

1. 空缓存环境拉取指定架构镜像并记录最终 image ID/多架构 digest，确认只拉所需组件
2. `up` → `check` → 宿主连接 → 真实业务读写/消息收发 → `down` → 再 `up`，验证数据保留
3. 首次初始化、重复启动、端口冲突、错误密码、不健康服务、构建失败的退出码与排障提示
4. 两门课程使用同一镜像引用；第二门不重复下载相同业务镜像，测试数据保持隔离
5. Apple Silicon 和 Intel/Linux amd64 分别记录实测结果；只看到上游多架构标签不能替代实测
6. 仅在一次性、已明确同意丢弃的实验项目中验证 `reset` 精确范围；不得清理用户已有卷
7. 预置前端的实际页面、API/业务链及后端/前端版本匹配证据

官方参考：[Compose profiles](https://docs.docker.com/compose/how-tos/profiles/)、[Testcontainers 配置](https://java.testcontainers.org/features/configuration/)、[Testcontainers 网络](https://java.testcontainers.org/features/networking/)、[Testcontainers 就绪等待](https://java.testcontainers.org/features/startup_and_waits/)。
