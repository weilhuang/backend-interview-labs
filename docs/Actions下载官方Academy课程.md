# 从 GitHub Actions 下载单一官方 Academy 课程

本入口面向私有仓库 `weilhuang/backend-interview-labs`。必须登录有仓库读取权限的 GitHub 账号。不会把课程二进制提交到 Git，也不会在聊天里上传二进制。

## 目前状态与首次实验

官方 smoke 运行 `36913605767` 已实际通过：单课 11 个 section、84 题、136 个占位区，966 个合同文件的学生导入字节、元数据及 JDK 21 / Gradle 8.10.2 均通过。此次 smoke 不代表完整 84 题原生测试或统一环境验收通过；发布仍需同一次 full-validation 与环境 job 的完整证据。早期本地 Unix socket 限制不再描述当前官方 runner 结果。Python 回归只验证门禁实现。

独立统一环境真实验收任务现已实现为第二个标准 Ubuntu job，但尚未在真实 Docker runner 执行。本候选仅完成普通功能重基与静态检查；压缩/PAX 边界独立验收仍未完成，整体为 `PARTIAL_NOT_APPROVED`。源码与 Python 合同回归、合成导入快照传输测试不能冒充运行成功。缺少第二个 job 的同归档完整成功证据时，最终 ZIP 仍被拒绝发布；旧分课 CI 或原生 84 个正例均不能代替它。

新工作流尚未进入默认分支时，GitHub 不提供它的 workflow_dispatch。开发期使用两个精确命名的受控验证分支，不需要提前合并新 PR：

1. 先让新 PR 的“课程分层验收”完成。必须全部 15 个任务、全部课程 suite 实际通过，不能把跳过算成通过
2. 从该次运行的 `ci-evidence-<run_id>-<attempt>` artifact 读取真正的 `tested_sha`。PR 的 API `head_sha` 常是作者分支提交，而实际测试可能是临时 merge commit，二者不能混用
3. 经维护者检查后，把 `academy-validation/smoke` 指向这个确切的已测 commit；该分支的 push 只启动官方导出/导入 smoke，固定使用 headless。现有源码 CI 的 push 仍仅监听 main，不重复跑一轮 15 个任务
4. smoke 通过后，可把 `academy-validation/full` 指向同一个已测 commit，启动完整官方验证。工作流会重新只读检查源 artifact 的 SHA256、运行/尝试号、仓库、实际 tested SHA、完整任务与 suite、当前 ref、真实 checkout、commit tree 和 parents；缺证据立即失败，不轮询等待绿灯
5. 工作流将来已经被正常纳入 main 后，才可从 Actions → “单一课程官方 Academy 打包” → Run workflow 选择 smoke/full。首次使用 headless；只有确认图形初始化阻塞后再选 xvfb，不绕过锁、协议或信任提示

官方验证执行 `validateCourse --tests true --links true`。84 个 Tests 必须完整匹配并全部成功；忽略、缺失、重复或未知结构会失败。链接门禁要求每题声明的 HTTP/HTTPS 源码链接全部出现，并要求全部已观察到的原生链接结果成功。当前 84 题合计 158 个去重后的每题 HTTP 预期；不声称裸相对 Markdown URL 都必然是原生命令支持的链接类型。

这是 V1 的一个课程、11 个章节、84 题、136 个练习区。V2/Go 尚未纳入本契约，扩展时必须更新映射及原生验收，不能沿用 V1 的绿灯。

## 下载与导入

只有完整原生验收与同归档真实统一环境门禁实际通过，运行详情页底部才会出现最终交付：

- `backend-interview-academy-<提交>-<运行>-<尝试>`：最终交付
- `academy-evidence-<提交>-<运行>-<尝试>`：原生过程报告
- `academy-environment-evidence-<提交>-<运行>-<尝试>`：真实环境逐命令结果、资源归属、前端截图与最终联合门禁
- `academy-intermediate-NOT-A-RELEASE-<提交>-<运行>-<尝试>`：两个 job 的验收中间产物，包含官方 ZIP 和官方已导入的学生/作者文件快照，仅保留 1 天。它在仓库 Actions 中可见，可能在后续环境验收失败时仍然存在，**不是发行包，不应作为课程交付下载**

普通成功/失败尽力保存证据；硬取消或 runner 故障可能来不及上传。

点击最终交付 artifact，浏览器会下载一个**外层 artifact ZIP**。先解压它，里面有：

- `backend-interview-academy.zip`：要导入 IDEA / JetBrains Academy 的官方课程 ZIP
- `SHA256SUMS`：该课程 ZIP 的 SHA256

请在 Academy 的本地课程导入入口选择里面的 `backend-interview-academy.zip`，不要选择外层 artifact ZIP。`gh run download <运行ID> -n <artifact名>` 会自动解开外层包装。可以在解压目录运行 `sha256sum -c SHA256SUMS` 核对原字节。

最终交付与验收证据只保留 7 天（中间产物为 1 天），过期需要重新执行授权的打包。长期 GitHub Release 上传不属于本工作流。

## 通过代表什么

工作流区分精确 tested commit 的源码 CI、官方导出、官方学生导入、实际 Gradle JVM、官方原生 Check、描述链接和官方作者导入。官方验证命令即使报告失败也可能退出 0，所以退出码绝不单独代表通过。

84 个原生 Check 使用各题实际配置的判题合同。命令行环境传入 `withDocker=true` 和 `dockerApiVersion=1.44`，但这不自动把每题所有独立 integrationTest 都并入原生 Check。已有分层 CI 继续提供原分课完整测试基线；新第二 job 验证统一导入布局、逐个真实服务和 C14 HTTP/浏览器/暂停恢复。此覆盖不声称穷尽所有网络故障窗口或所有操作系统体验。统一包的原生 GUI Check/Reset 和官方学习者负控仍是单独验收项，报告保留 `NOT_RUN`，不捏造 UI 成功。

官方规则会省略 `.courseignore`、Wrapper 程序与 JAR；不能假定官方插件会补齐 Wrapper。统一课程使用 `bash scripts/gradle.sh`，首次显式 `prepare --download` 或 `prepare --zip /绝对路径/gradle-8.10.2-bin.zip`，校验仍保留的 `gradle-wrapper.properties` 中固定 URL/SHA256 并在课程树外准备 SDK。普通 Gradle 执行不自动下载；`verify` 为只读校验。使用 Bash 调用，不要求导入后脚本具有执行位。`gradle-wrapper.properties`、构建脚本、题目文件、测试、公共支撑和环境入口均按实际导入内容逐文件核对。官方包内部的加密字节不被重写。

## 运行资源与费用边界

仅使用标准 `ubuntu-24.04`，无付费大 runner、无定时任务、无预算或账号改动。私有仓库会消耗 GitHub Actions 配额；此工作流不读取或修改账户额度。

- IDEA 下载约 1.58 GB，解压约 4.2 GB；安装前需至少 10 GiB 可用空间
- 首轮不建立 IDE/Gradle/Docker 缓存，避免大缓存复制、缓存存储及陈旧结果风险；IDEA 下载临时包校验解压后即删
- Docker 重检查按课程已有顺序按需启动，不预拉所有镜像，不一次启动全部共享服务
- 原生测试前需至少 4 GiB 空间；运行中低于 2 GiB 即失败并停止当前 CLI 进程组，不清理宿主 Docker/系统目录
- native-package：smoke job 上限 25 分钟；full job 上限 80 分钟。导出最多 5/10 分钟，84 题及链接最多 45 分钟；各步骤上限保留证据收集余量
- real-environment：独立标准 runner、job 上限 65 分钟，其中顺序运行脚本上限 50 分钟，留有工具准备、下载、证据与上传余量；不再安装 IDEA。每条命令另外具有不超过 20 分钟的超时、4 MiB 原始输出上限及 2 GiB 剩余磁盘门槛
- full 的两个 job 串行，最坏 job 时间预算合计 145 分钟；这不是实测耗时或费用承诺。首轮不创建依赖/镜像缓存，也不自动重试全量任务
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

## 两个 job 如何验证同一个课程

1. 第一 job 重新只读核对精确 tested commit 的既有源码 CI，生成单课作者树，用固定官方 CLI 导出并抓取原字节 ZIP，验证官方学生与作者导入及全部 84 题/链接。源代码不是 CLI 的清理目标
2. 它仅把合同白名单中的普通文件传入中间 ZIP_STORED（不压缩）容器：同一官方 ZIP、native summary、source contract，以及已经逐文件验证的官方学生/作者导入。每文件绑定 SHA256、大小和安全 mode；不递归打包 IDE 配置、Gradle 缓存、build、`.env`、日志或符号链接
3. 第二 job 按精确 artifact 名下载同一 run/attempt 中间产物，并以第一 job 输出的 SHA256 再校验。解包前核对仓库、真实 tested commit、run/attempt、ZIP/contract hash、完整文件库存、安全相对路径和 mode；中间容器仅使用标准库 ZIP_STORED，拒绝其他压缩方式和非常规文件类型。Python 标准库会在检查 4000 项上限之前解析中心目录并分配条目对象；总容器字节上限不能视为严格的最坏内存或 CPU 上限。限制总容器 264 MiB、总载荷 256 MiB、单文件 128 MiB、4000 项、UTF-8 路径 1024 字节/32 层/单段 255 字节；先核对库存与总大小，再读取成员并在新目录中写入。官方课程 ZIP 作为其中一个普通文件按原字节传递，不重新压缩、修改或生成。再次验证学生/作者明文与原生元数据
4. 运行使用这些**官方导入快照**，没有作者源码复制回退。先证明导入中缺少三个被排除的 Wrapper 程序/JAR，学生和作者的统一入口可用，再准备并验证固定 Gradle SDK。学生起点不执行应当失败的业务正例，其状态为 `NOT_RUN_EXPECTED_STARTER`
5. 唯一镜像台账来自导入课程；Docker API 固定 1.44。专属 `totalacademy-ci-运行号-尝试号` 及 `-capstone` 项目启动前必须没有容器、卷或网络。端口是新分配的回环端口，启动后还核对实际发布绑定、精确 Compose 目录/配置标签、服务、镜像引用和挂载
6. MySQL、Redis、Kafka、RocketMQ 逐个执行 `start → doctor → health → 实际绑定 → 宿主真实写读 → stop保卷 → start → 只读原标记 → stop`。宿主 JDBC、RESP、Kafka 和 RocketMQ SDK 走实际发布的回环端点。Java 探针仅复用导入课程严格锁定的 messaging-support 运行图中的外部客户端模块，不新建 Maven 依赖图；明确排除统一根注入的 environment-ledger 项目输出，不把尚未构建的项目 JAR 当外部依赖。RocketMQ 重启读取的是停止前留下的未消费消息，不重发伪造持久化
7. C14 从 `05-defense` 的真正 installDist 启动，运行统一 workbench-check 和随课提供的原 browser-smoke，覆盖提交、同号重试、409 冲突、取消、Kafka/gRPC 投影以及 320/390/800/801/1440 像素视口。CI 单独装固定 Playwright；学生使用提供的前端不需要 Node
8. 通过统一 `pause-service/recover-service` 暂停和恢复 orders、delivery；核对已确认订单仍在、配送停止时 replay 返回 503 且确有积压、恢复后同号投影与取消审计一致。容器 ID 与原阶段挂载必须不变，不默默切换到其他检查点
9. 运行后再次核对所有导入合同源文件字节。每个必需检查都须有实际命令、退出码、超时上限、耗时和输出 SHA，并核对完整位置参数、客户端类/脚本、实际端口、请求路径/状态/内容和本次标记；缺失、跳过、仅健康检查、dry-run、echo、仅 --help/-version 等假证据均不能放行
10. 普通 stop 先证明卷与容器保留；最后清理仅限启动前证明不存在、拥有精确本次 CI 标签/目录的临时容器、卷、网络。不会调用全局 prune、删除用户默认卷或读取外来容器日志。失败时也尝试同范围清理；runner 丢失/硬取消只能由临时 VM 生命周期收尾

最终 `release_gate.py` 同时核对 native 与 environment 的仓库、commit、run/attempt、官方 ZIP、合同和中间产物 SHA，以及完整必需检查；还会在发布时重新以不跟随链接的方式读取实际 ZIP，核对字节数与所有证据中的预期 SHA，再创建独立只读发行副本；SHA256SUMS 只来自这些已验证的字节。仅上传这份通过门禁的副本到 `backend-interview-academy-*`，不对被替换的 ZIP 重新计算校验值来冒充通过。这条串行 artifact 交接没有等待自身源码 CI 再跑一轮的循环依赖。

### 私有无压缩交接候选的验证范围

ZIP_STORED 简化移除了自定义 gzip/tar/PAX 处理。旧 R2 的压缩/PAX 独立审查仍未完成，不能据此改标通过。适用范围仅限同一受信任工作流生产、经同 run/attempt 输出 SHA256 绑定的中间产物；不接受任意外部 ZIP。当前仅验证正常受信任生产者到消费者的合成文件往返、身份不匹配、普通内容意外变化及模式丢失；不代表异常容器/元数据、资源耗尽、竞态或全面安全验证。真实官方双导入、native84 与真实环境验收仍须同次受控运行证据。保留标准 runner 80+65 分钟上限、NOT-A-RELEASE 标识、仓库 Actions 读者可见和一天留存；不提前发布。


## 同一验收会话内的正常协议界面

运行 `36930053754` 的官方导出、967 文件严格学生导入及 Gradle/JDK 检查通过，但原生验证在初始化阶段超时。独立截图与线程证据确认它等待 JetBrains User Agreement 2.0（2025 年 4 月 10 日）正常界面，84 题与后续真实环境并未执行。用户已阅读该固定安装包的完整协议并授权正常界面接受。云桌面实测完成了勾选、Continue 和拒绝可选遥测；同 profile 的缺失归档输入在 4 秒内得到官方导入错误及退出码 1，只证明官方 starter 已越过协议界面，不代表课程通过。

完整 Actions 使用同一个 fresh runner/profile/Xvfb/官方 validateCourse 进程逐阶段观察，不写入接受偏好、不复制任何旧 profile。固定内置 HTML SHA256 为 `96530426ef62cd0eca629350c3ab5afb552c518868a0edbbce85ea5e0f713516`。每个阶段先保存本次专用显示器截图到 `academy-ui-stage-阶段-运行-尝试` artifact，维护者实际看图确认同一协议与控件后，才在专用 `academy-control/eua-ui` ref 写入该次运行、尝试、阶段对应的小 JSON。ref 不触发工作流，runner 只读；不得提前写动作。

机械记录仅含 schema、run_id、run_attempt、stage、screenshot_sha256、eua_sha256、action。允许动作只有 `CHECK_EUA`、`CONTINUE_EUA`、明确拒绝遥测的 `DECLINE_USAGE`，不接受坐标、文本、shell 命令或其他按钮。本次Xvfb wrapper/server与IDE的PID、start ticks、UID、session/pgrp，以及专用socket和Xauthority文件inode分别建立身份记录。每次截图或动作前复核；已核pidfd传入JBR并在实际点击前再次核其对应进程未退出。实际动作前再次核对完整截图字节；不一致、过期、重放或错误身份均失败。固定图形布局的动作点必须在当次图中确实位于对应控件内，布局变动时停报，不自动猜测适配。协议摘要与截图核对是本次受信任固定工具链的操作边界，不是面向任意恶意桌面的全面安全保证；图像校验与点击之间仍有极短的不可原子化窗口。

UI 总子预算 300 秒（包括图像交接和批准等待）绑定本次IDE进程的kernel start ticks并计入原 validateCourse 2700 秒；官方全阶段的唯一 60 分钟绝对截止绑定已启动监督进程的kernel start ticks，跨步骤不重置；native job 80 分钟、environment job 65 分钟和真实环境 50 分钟预算不变。单个 workflow 等待步骤的取消上限不能用于延长这些合并预算。新协议、商业许可、账号或 Trust 不在动作集合内，必须停止并单独确认。只清理本轮登记的 pidfd 所代表进程，不接管 PID 重用后的其他进程。登记仅沿已核验父进程的当次 task/children 子链，打开句柄前后复核 start ticks、UID、PPID、session/pgrp 及父句柄；不扫描全局进程表，不补收养身份不明对象。清理证明仅限已登记集合，未登记或脱离子链的后代由 fresh runner 生命周期收尾，不能宣称整棵派生树已清空。

`academy-ui-receipts-运行-尝试` 在第三阶段后及时提供前后截图、拒绝遥测后的画面、显示器身份和执行回执，一天后过期。它们不含 profile、环境变量、token 或课程 ZIP；硬取消仍可能来不及上传。UI 操作成功不替代 source CI、84 个 Tests、链接、严格导入、61 个真实环境检查或最终 hash/清理门禁。任何辅助代码变更均先进入 PR 的新 source CI，通过后才以新 `tested_sha` 启动完整验证，不沿用旧提交绿灯。
