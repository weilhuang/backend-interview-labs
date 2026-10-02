# 独立课程镜像台账

本目录由仓库根的 `python scripts/sync_course_versions.py` 自动生成。唯一版本来源是 `infra/versions.env`，不是第二份人工维护的版本表。更新版本时先修改根台账，再重新生成并运行 `python scripts/sync_course_versions.py --check`。

## 源码仓库与独立包

- 完整仓库：Gradle 向父目录查找 `infra/versions.env`，并拒绝与课程快照不一致的版本
- 独立课程：保留本 `shared` 目录，直接读取 `versions.env`；同目录 `versions.env.sha256` 会校验内容，`source-manifest.json` 保留来源与 SHA256
- 清单和读取器都登记在课程 `course-info.yaml` 的 `additional_files`；生成教案或普通学员副本后仍须保留这些文件
- SHA256 检查发现误改或传输差异，不等于发布者数字签名，也不代表已核验镜像 digest、架构支持或安全漏洞

## 显式覆盖与错误边界

可设置 `LAB_SHARED_VERSIONS=/绝对路径/versions.env`，或 `LAB_REPO_ROOT=/完整仓库根目录`。优先级为 Gradle/JVM 的 `lab.versions` 系统属性、`LAB_SHARED_VERSIONS`、兼容旧 Redis 副本的 `LAB_VERSIONS`、`LAB_REPO_ROOT`、自动发现。显式路径不存在时立即失败，不回退到另一份台账。请使用绝对路径，避免不同工作目录造成含义变化。

Gradle 为全部 Test 和 JavaExec 任务传入同一解析后的路径，并从台账设置 `TESTCONTAINERS_RYUK_CONTAINER_IMAGE` 与 `TESTCONTAINERS_TINYIMAGE_CONTAINER_IMAGE`。直接在 IDE 启动 JUnit 而不通过 Gradle 时，也需要设置这两个辅助镜像环境变量；值读取本台账中的 `TESTCONTAINERS_RYUK_IMAGE` 和 `TESTCONTAINERS_TINY_IMAGE`，不能手写默认标签。推荐使用 Gradle 委托测试。

`verifyCourseVersions` 只做台账、校验和及测试配置检查，不启动容器。独立包不需要父仓库；首次 Gradle/Maven 依赖下载仍需要网络，离线构建需要预先准备相同依赖缓存。真实数据库/Redis 验收仍需要 Docker，快照读取通过不代表集成通过。

## 运行入口

源码仓库或普通源码分发目录保留 Wrapper 时，可在课程根运行 `./gradlew verifyCourseVersions`，再运行课程 README 中的具体检查任务。Academy 官方导出可能移除 `gradlew`、`gradlew.bat` 与 `gradle-wrapper.jar`；这类 ZIP 使用 IDE 的 Check/Run 或 Gradle 工具窗口，不要求目录中存在 `./gradlew`。原生插件导出与干净导入是否实测，仍以课程验收报告为准。
