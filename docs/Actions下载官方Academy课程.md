# 从 GitHub Actions 下载单一官方 Academy 课程

本入口面向私有仓库 `weilhuang/backend-interview-labs`。必须登录有仓库读取权限的 GitHub 账号。不会把课程二进制提交到 Git，也不会在聊天里上传二进制。

## 目前状态与首次实验

固定官方 CLI 的本地尝试被运行环境的 Unix socket 限制挡在 IDEA 启动阶段，退出码 3；没有本次统一课程导出、导入或原生测试成功证据。Python 回归只验证门禁实现。

当前还未实现统一环境入口的独立真实 Docker 验收任务。即使完整原生 84 题通过，最终 ZIP 发布仍会明确阻塞，报告 `unified_environment_runtime=NOT_RUN`。旧分课 CI、模拟测试与 84 个原生正例都不能替代这一步。

新工作流尚未进入默认分支时，GitHub 不提供它的 workflow_dispatch。开发期使用两个精确命名的受控验证分支，不需要提前合并新 PR：

1. 先让新 PR 的“课程分层验收”完成。必须全部 15 个任务、全部课程 suite 实际通过，不能把跳过算成通过
2. 从该次运行的 `ci-evidence-<run_id>-<attempt>` artifact 读取真正的 `tested_sha`。PR 的 API `head_sha` 常是作者分支提交，而实际测试可能是临时 merge commit，二者不能混用
3. 经维护者检查后，把 `academy-validation/smoke` 指向这个确切的已测 commit；该分支的 push 只启动官方导出/导入 smoke，固定使用 headless。现有源码 CI 的 push 仍仅监听 main，不重复跑一轮 15 个任务
4. smoke 通过后，可把 `academy-validation/full` 指向同一个已测 commit，启动完整官方验证。工作流会重新只读检查源 artifact 的 SHA256、运行/尝试号、仓库、实际 tested SHA、完整任务与 suite、当前 ref、真实 checkout、commit tree 和 parents；缺证据立即失败，不轮询等待绿灯
5. 工作流将来已经被正常纳入 main 后，才可从 Actions → “单一课程官方 Academy 打包” → Run workflow 选择 smoke/full。首次使用 headless；只有确认图形初始化阻塞后再选 xvfb，不绕过锁、协议或信任提示

官方验证执行 `validateCourse --tests true --links true`。84 个 Tests 必须完整匹配并全部成功；忽略、缺失、重复或未知结构会失败。链接门禁要求每题声明的 HTTP/HTTPS 源码链接全部出现，并要求全部已观察到的原生链接结果成功。当前 84 题合计 158 个去重后的每题 HTTP 预期；不声称裸相对 Markdown URL 都必然是原生命令支持的链接类型。

这是 V1 的一个课程、11 个章节、84 题、136 个练习区。V2/Go 尚未纳入本契约，扩展时必须更新映射及原生验收，不能沿用 V1 的绿灯。

## 下载与导入

待独立真实统一环境门禁补齐并实际通过、完整原生验收也通过后，运行详情页底部才会出现最终交付。当前仅有证据输出：

- `backend-interview-academy-<提交>-<运行>-<尝试>`：最终交付
- `academy-evidence-<提交>-<运行>-<尝试>`：小型过程报告；普通成功/失败尽力保存；硬取消或 runner 故障可能来不及上传

点击最终交付 artifact，浏览器会下载一个**外层 artifact ZIP**。先解压它，里面有：

- `backend-interview-academy.zip`：要导入 IDEA / JetBrains Academy 的官方课程 ZIP
- `SHA256SUMS`：该课程 ZIP 的 SHA256

请在 Academy 的本地课程导入入口选择里面的 `backend-interview-academy.zip`，不要选择外层 artifact ZIP。`gh run download <运行ID> -n <artifact名>` 会自动解开外层包装。可以在解压目录运行 `sha256sum -c SHA256SUMS` 核对原字节。

Artifacts 只保留 7 天，过期需要重新执行授权的打包。长期 GitHub Release 上传不属于本工作流。

## 通过代表什么

工作流区分精确 tested commit 的源码 CI、官方导出、官方学生导入、实际 Gradle JVM、官方原生 Check、描述链接和官方作者导入。官方验证命令即使报告失败也可能退出 0，所以退出码绝不单独代表通过。

84 个原生 Check 使用各题实际配置的判题合同。命令行环境传入 `withDocker=true` 和 `dockerApiVersion=1.44`，但这不自动把每题所有独立 integrationTest 都并入原生 Check。特别是 C14 等课程，完整集成、恢复和浏览器验收仍由已有分层 CI 提供原分课基线；统一环境入口仍须独立真实验收。统一包的 UI Check/Reset、学习者负控和所有环境编排体验仍是单独验收项；报告明确保留 `NOT_RUN`，不会捏造 UI 成功。

官方规则会省略 `.courseignore`、Wrapper 程序与 JAR；导入后由官方插件补齐 Wrapper。`gradle-wrapper.properties`、构建脚本、题目文件、测试、公共支撑和环境入口均按实际导入内容逐文件核对。官方包内部的加密字节不被重写。

## 运行资源与费用边界

仅使用标准 `ubuntu-24.04`，无付费大 runner、无定时任务、无预算或账号改动。私有仓库会消耗 GitHub Actions 配额；此工作流不读取或修改账户额度。

- IDEA 下载约 1.58 GB，解压约 4.2 GB；安装前需至少 10 GiB 可用空间
- 首轮不建立 IDE/Gradle/Docker 缓存，避免大缓存复制、缓存存储及陈旧结果风险；IDEA 下载临时包校验解压后即删
- Docker 重检查按课程已有顺序按需启动，不预拉所有镜像，不一次启动全部共享服务
- 原生测试前需至少 4 GiB 空间；运行中低于 2 GiB 即失败并停止当前 CLI 进程组，不清理宿主 Docker/系统目录
- smoke 总预算 25 分钟，各步骤上限合计 24 分钟；full 总预算 80 分钟，各步骤上限合计 78 分钟，已含收集/上传余量。smoke 导出最多 5 分钟；full 导出最多 10 分钟，84 题及链接最多 45 分钟。预算是上限，不是已测耗时
- 超时、空间不足、新协议/登录/信任提示、SDK 选择失败或未知 CLI/JSON 变化都尽力保留有界证据并停止，不自动接受条款或降低检查标准；runner 丢失/硬取消不能保证留下 artifact

## 固定版本与证据

IDEA 2026.1.5 / build 261.27258.48 与 Academy 2026.9-2026.1-1070 的官方 URL、SHA256、校验来源在 [`scripts/academy/toolchain.json`](../scripts/academy/toolchain.json)。IDEA 使用官方公布 SHA256；Academy SHA256 来自已下载官方 Marketplace 文件的本地测量，不冒称上游签名校验。

证据文件通过不跟随符号链接的读写边界收集，输出目录必须是独立新目录；损坏的诊断 JSON 会被省略并记录原 SHA，不阻止其他失败证据保存。诊断文本和 JSON 会尽力遮盖凭据字段、Authorization 与带认证信息的 URL，不上传整个配置/环境或原始完整日志。

JDK21 路径通过 Academy 官方 `project.jdk` 属性指定；IDEA 自身仍运行 bundled JBR。Gradle init observer 记录真正的 `java.version`、`java.home`、Gradle 版本与项目根，缺证据或非 Java21 即失败。

技术依据：
- [官方 CLI 创建/清理目标目录](https://github.com/JetBrains/educational-plugin/blob/6b77322dcfc0fbab8c3e94ab5055b3f72d74460c/intellij-plugin/features/command-line/src/com/jetbrains/edu/commandLine/EduCourseProjectCommand.kt)
- [官方 JDK 默认参数](https://github.com/JetBrains/educational-plugin/blob/6b77322dcfc0fbab8c3e94ab5055b3f72d74460c/intellij-plugin/jvm-core/src/com/jetbrains/edu/jvm/environment/JdkLanguageEnvironmentCatalogProvider.kt)
- [官方验证 JSON 类型](https://github.com/JetBrains/educational-plugin/blob/6b77322dcfc0fbab8c3e94ab5055b3f72d74460c/validation-results/src/com/jetbrains/edu/coursecreator/validation/ValidationResultNode.kt)
- [GitHub artifact 下载说明](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/download-workflow-artifacts)

## 待补齐的真实统一环境门禁

应在与 IDEA 打包分开的标准 Ubuntu job 中，用新的独立课程目录与本次专属项目名/端口，按 profile 顺序执行 `start → doctor/health → 代表性真实写读 → stop`。MySQL、Redis、Kafka、RocketMQ 逐个运行；C14 还需统一 `start capstone --stage 05-defense`、`health`、`workbench-check`、保留的浏览器流程与故障恢复脚本。只能停止本次拥有的资源，不能全局 prune。健康探针本身不替代集成判题。该任务尚未实现、未运行，所以当前发布锁不能从输入参数或环境变量解除。
