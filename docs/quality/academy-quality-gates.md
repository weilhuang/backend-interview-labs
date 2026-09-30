# Academy 课程质量门禁

本仓库把课程质量拆成互补的证据，避免把普通 JUnit、ZIP 存在、或代表题 GUI 抽检误称为“全部题目原生 Academy 验收”。统一 Java 基线是完整 JDK 21。所有新门禁都不修改作者工程、已交付的官方 ZIP 或打开的 IDEA 项目。

## 验收金字塔与计数口径

从快到慢保留四层互补证据：①静态元数据、课程资产和判题器自测；②参考解、整题学员起点与逐编码区合同测试；③必要的真实网络/数据库/broker与持久化恢复；④原生IDEA的Check、Reset、导出/导入及可见界面。下一层不能由上一层的绿灯推断；上层真实系统测试也不能自动证明每个可编辑方法被调用。每层只报告实际执行范围，不把同一题的多层验证重复相加为新题数。

## 1. 官方实际上提供什么

2026-09-30 阅读的[官方课程制作指南](https://plugins.jetbrains.com/plugin/10081-jetbrains-academy/docs/educator-start-guide.html)要求作者提供答案与测试、添加占位区，然后用课程预览检查学习者可见文件、提示、错误答案和正确答案反馈。正式 ZIP 由 **Course Creator → Create Course Archive** 导出，导出对话框可以勾选 **Check all tasks**。学习者通过 **Browse Courses → My Courses → Open course from disk** 导入。导出前批量测试不能代替这些学习者流程。

官方插件源码固定在 [453127c6a415af07cbb2e6827e1104c5d95a0e9c](https://github.com/JetBrains/educational-plugin/tree/453127c6a415af07cbb2e6827e1104c5d95a0e9c)，便于复核行为。这个源码快照没有被证明等同于已安装二进制的构建提交；已安装组合另为 IDEA 2026.1.5 / Academy 2026.9-2026.1-1070。

- [CCCheckAllTasksAction](https://github.com/JetBrains/educational-plugin/blob/453127c6a415af07cbb2e6827e1104c5d95a0e9c/intellij-plugin/educational-core/src/com/jetbrains/edu/coursecreator/actions/checkAllTasks/CCCheckAllTasksAction.kt) 是作者模式下的 IDE action，ID 为 `Educational.Educator.CheckAllTasks`
- [checkAllTasksUtil](https://github.com/JetBrains/educational-plugin/blob/453127c6a415af07cbb2e6827e1104c5d95a0e9c/intellij-plugin/educational-core/src/com/jetbrains/edu/coursecreator/actions/checkAllTasks/checkAllTasksUtil.kt) 遍历所选课程/章节/任务，调用真实 checker 并要求 `Solved`。它不生成错误解，也不验证导入、显示或 Reset；理论题和未选择答案的选择题有专门的跳过逻辑。本仓库当前门禁只接受普通 `edu` 题
- [导出前批量检查](https://github.com/JetBrains/educational-plugin/blob/453127c6a415af07cbb2e6827e1104c5d95a0e9c/intellij-plugin/educational-core/src/com/jetbrains/edu/coursecreator/actions/CheckAllTasksBeforeCreateCourseArchiveProgressTask.kt) 遇到失败仍提供“继续创建归档”分支。因此 ZIP 生成成功本身不是全题通过证据
- [CheckAllTest](https://github.com/JetBrains/educational-plugin/blob/453127c6a415af07cbb2e6827e1104c5d95a0e9c/intellij-plugin/educational-core/testSrc/com/jetbrains/edu/coursecreator/actions/CheckAllTest.kt) 用插件测试夹具与 `checkResultFile` 验证 action 行为；[CCCreateCourseArchiveTest](https://github.com/JetBrains/educational-plugin/blob/453127c6a415af07cbb2e6827e1104c5d95a0e9c/intellij-plugin/educational-core/testSrc/com/jetbrains/edu/coursecreator/archive/CCCreateCourseArchiveTest.kt) 验证插件自己的序列化。它们不是可以对任意课程 ZIP 直接执行的现成验收命令
- [官方 Java 模板](https://github.com/jetbrains-academy/java-course-template)附带 [Gradle Build workflow](https://github.com/jetbrains-academy/java-course-template/blob/c23b40acc8e1a0628e036598935ee6139cca0077/.github/workflows/gradle-build.yml)，实际执行 `build --stacktrace`，负责课程代码测试。不能把它描述成 Academy 导出、导入、Check、Reset 的 UI Action

在这些官方文档、模板和固定源码中，未发现受支持的“一条 CLI 对任意课程执行上述完整原生链路”的接口。这是本次核实范围内的结论，不是声称所有 JetBrains 内部工具都不存在。

## 2. 每次变更的轻量门禁

```sh
python -m pip install -r scripts/quality/requirements.txt
python -m unittest discover -s scripts/quality/tests -v
python scripts/quality/academy_gate.py legacy-metadata \
  --report build/quality/academy-legacy-metadata.json
```

默认自动发现 `courses/` 下的全部课程根，包括 MySQL、Redis 两个子工程。可重复指定 `--course java-foundations`、`--course data-storage/mysql-engineering` 缩小范围。

`legacy-metadata` 先运行下列通用检查，再在临时作者树中复用全部10课原有静态 validator（含必需教学标题、完整标准解、调用示例、代码围栏、固定源码与版本同源约束），不会改写当前 checkout 的报告；`metadata` 可单独只运行通用检查。

检查课程目录引用、孤立题目、重复 YAML 键、重复资产、路径逃逸/符号链接、公开可见文件、题目漏列资产、Gradle 运行文件、占位区排序与 UTF-16 边界，以及每个答案片段在公开题面/答案文件中确实存在。中文及 emoji 不能按 Python 字符下标替代 IntelliJ UTF-16 偏移。

这些是**仓库的作者契约**，不是完整的 Academy YAML Schema；不支持的题型/框架式逐步课会明确失败，要求新增适配。这里也不模拟 `.courseignore` 的所有原生语义，官方归档另验。

当前扫描范围为 10 个课程工程、96 道编码题、156 个占位区；这与课程规划文档里的实验单元数不是同一种计数。

## 3. 真 Gradle 的课程包闭环

```sh
python scripts/quality/academy_gate.py roundtrip \
  --course java-foundations --suite contract \
  --java-home "$JAVA_HOME" \
  --report build/quality/foundations-roundtrip.json \
  --work-dir build/quality/foundations-roundtrip-new
```

每个课程依次执行：

1. 仅按显式课程/任务/附加资产清单制作确定性源码测试包，生成每文件 SHA-256
2. 校验包清单与内容后解包到全新目录，并再次从解包后的元数据解析课程
3. 按真实 UTF-16 占位生成全部学习者起点；真实 Gradle 执行全题，**每题**必须有失败测试
4. 从不可变测试包恢复参考解；同一个独立工程重新执行全题，**每题**全部通过
5. 再解包到第二个全新目录；学习区摘要必须与第一次完全相同，随后**每题**再次失败
6. 确认作者输入在验证期间没有发生变化

默认使用包内 Wrapper，可用 `--gradle /existing/trusted/gradle` 指定已有官方 Gradle。所有阶段单 worker、`--no-daemon`、`clean`、`--rerun-tasks`、`--no-build-cache`。保留依赖缓存，不能复用测试结果。需要复用依赖时使用独立的 `--gradle-user-home`；不要与正在工作的 IDEA 共享活动缓存锁。`--offline` 和重复的 `--gradle-arg=...` 可复用已有依赖仓库；自定义 init script 和仓库差异必须随证据披露。不要关闭 TLS 或绕过网络限制。

失败不能只看退出码：负向 Gradle 必须以标准测试失败码1退出，信号终止不算通过。每个选中题目都必须产生新的 JUnit XML、执行测试大于零、零 skip。空解要求测试失败，参考解要求零失败；编译失败、依赖缺失、没发现测试、启动异常或超时都使门禁失败，不能充当“错误答案被拒绝”。XML还逐一核验真实testcase与失败数量；依赖、初始化、容器启动、端口占用、OOM、未知失败不能由同题另一条TODO失败兜底。只有断言、带已审占位消息的TODO异常及有直接服务端TODO证据的少量Spring适配被归因；新异常形态先失败再审查。报告包含逐题数量、真实 Gradle 命令、退出码和日志路径。

**源码测试包不是官方 Academy ZIP，第二次解包也不是插件的 Reset。** 这条链路验证声明资产组成的独立 Gradle 工程，不验证插件导入器、Check 按钮、题面排版或交互状态。报告始终保留 `native_idea/native_archive_export_import/native_reset=NOT_RUN`。

## 4. 纯合同与真实服务分层

默认 `--suite contract`：MySQL、Redis 使用现有 `unitTest`，其余课程使用现有 `test`。不会在后台偷偷启动 Docker。本轮已证实Redis 04一致性、05复制、06租约三个学员起点在纯unitTest全过：对应结果明确标为 `INTEGRATION_REQUIRED`。该课程的纯合同模式完成后整体仍为 `INTEGRATION_REQUIRED`、非零退出，不是学员拒绝通过。必须另运行真实integration模式。未知的未拒绝题则直接FAIL。不能把其他测试的成功当作该学习区已受测。

已有 Docker 的隔离发布环境可以显式执行：

```sh
python scripts/quality/academy_gate.py roundtrip \
  --course messaging --suite integration \
  --java-home "$JAVA_HOME" \
  --report build/quality/messaging-integration-roundtrip.json \
  --work-dir build/quality/messaging-integration-new
```

真实服务分层使用现有 Testcontainers/Gradle 入口：

| 课程 | 实际命令 | 集成题范围 |
|---|---|---|
| MySQL | `test`，仅统计带 integration 标签的类 XML | 7 题 |
| Redis | `integrationTest` | 7 题 |
| Kafka/RocketMQ | `test -PwithDocker`，仅统计带 docker 标签的类 XML | 12 题 |
| 分布式 | `integrationTest` | 05 幂等、06 事务、07 Outbox/缓存、08 容量，共 4 题 |
| Spring/Boot | `:03-transactions:integrationTest` | 事务题 1 题 |
| 综合项目 | `integrationTest` | 02–05，共 4 题；04 为观察型 |

合计 35 个集成题入口，其中 34 个要求学习者错误被集成测试拒绝。C14 第 4 阶段的 `RecoveryIntegrationTest` 通过 `RealServices` 重启 MySQL，不调用该题可编辑的 `RecoveryPolicy`：它被明确标为 `OBSERVATION_ONLY`，要求系统观察测试成功；该学习区判题由合同测试负责。其他没有独立集成入口的题逐一记录 `NOT_APPLICABLE`，仍须通过合同门禁，不能被表格外推为“全覆盖”。

集成模式先检查真实 Docker 服务。它会创建测试容器并执行已有故障/恢复场景，只能在隔离测试环境按需运行。不要每次报告文字修改都运行三遍容器套件；通常每次变更运行轻量门禁，按当前PR累计变更范围选择对应既有课程workflow，发行或手动强制时做全量；不建立跨run通过证据复用状态机。云端本地没有Docker，不能运行此模式。首轮新门禁GitHub CI（b79832d）已使Redis真实三阶段通过19项/13失败→0失败→13失败；MySQL则暴露05死锁政策学习区未被原集成测试触达，已补真实1213/1205/1062错误判定测试，等待下一提交CI。原有Docker测试的通过记录不会自动升级为新门禁通过；详见中文阶段报告。

### CI 每课一次命令的最小接法

现有9个workflow负责10个课程工程：MySQL、Redis选 `--suite integration`；其余8课（试点、Java基础、并发、JVM、框架、分布式、综合、消息）选 `--suite contract`。后8课已有纯合同证据能拒绝各题起点，同时保留原来全部真实服务测试。无需为了每个编码区在所有层都失败而重复三倍容器工作。

用 `--work-dir "$GITHUB_WORKSPACE/build/quality/roundtrip-课程"` 保存临时包/项目，报告放 `build/quality/`。上传JSON、源码清单、各phase日志与全新JUnit XML；不必上传整个源码fixture或编译树。首轮每phase600秒、step35分钟、DB job60分钟预算，若确有超时根据原始日志再调整，不能无上限等待。

## 5. 每个可编辑区独立受测

“整题全部置空失败”可能只说明其中一个方法被测试命中。新增依赖轻量课程审计，保留其他所有参考实现，每次仅将**一个**占位区替换为其真实学员起点，重新严格编译整题并执行 JUnit：

```sh
python scripts/quality/placeholder_audit.py \
  --course java-foundations --course java-concurrency \
  --course java-jvm --course java-recovery-collections \
  --java-home "$JAVA_HOME" \
  --junit-console /path/to/junit-platform-console-standalone-1.11.4.jar \
  --report build/quality/placeholder-audit.json \
  --work-dir build/quality/placeholder-audit-new
```

JUnit JAR 校验固定 SHA-256；不下载或执行未知程序。每题先证明完整参考实现通过，再逐区替换；读取新鲜JUnit XML并与控制台计数交叉核对。Console Launcher把预期TODO异常记为error时仅按已审核消息规范化，再共享严格故障归因；编译错误、无测试、未知异常、信号退出、skip、aborted 均不能算拒绝。幸存变体导致 FAIL。

本轮四个核心工程43题、76个可编辑区的最终严格独立审计均通过：基础29区用保留的新鲜XML及精确编译输入复核，C02 17区、JVM10区和试点20区按最终脚本重新执行，零幸存变体。逐项结果见[中文阶段报告](中文阶段报告.md)和[机器摘要](verification-summary.json)。初轮失败数量审计暴露了C02子任务TODO被生产者等待超时遮住的问题；公开测试及生成器已改为按完成顺序传播异常，取消同伴并有界清理，没有加入超时豁免。这是完整 JDK 21 的 `javac --release 21` + JUnit 证据，**不是 Gradle 或 IDEA**。当时其余六个依赖丰富工程的80个占位区未由此脚本逐区审计；下节记录后来独立补验的37区，不能归为本脚本支持范围；当前脚本主动拒绝不支持的课程，而非偷偷使用不完整类路径。既有正解/错解/替代正确解验证器继续保留，这个门禁不取代它们，也不是全面变异得分或生产正确性证明。

本轮历史 Gradle 报告须与最终证据边界一起读：Framework的15份运行说明在验证中变化，属于旧资产快照。分布式gRPC客户端UNKNOWN曾被最终分类器正确拒绝；现已修复02/08题同一次RPC的原始服务端异常传播，并由最终严格脚本重跑8题三阶段，当前48测试/37失败→0失败→37失败；历史44项快照不冒充新源码。没有增加RPC异常通用豁免。其余保留XML重检也不等于重新执行三阶段。

### 补充的依赖丰富合同区与真实服务区

在已绿的 `e66c2fddf2ce172b140e9a577e43c9828f9307a1` 输入上，另完成37个独立声明编码区的真实JDK21编译/JUnit审计：frameworks 9区、distributed 21区、capstone 7区。**36区使用完整模块合同测试；Admission.execute的1区只使用既有选定JUnit方法** `CapacityTest#入口无等待拒绝与异常许可归还`。其原完整变体套件出现额外RPC诊断错误，仍保留为 `UNCLASSIFIED_FAILURE`，不能改称完整套件通过。另有两个屏障断言不作为严格拒绝依据；对应编码区由直接本区TODO失败证明。

这37区是原76区之外的补充证据，合计113个独立编码区；不是113道题，不是全156区，也不是通用变异覆盖率。完成这两批时还有43区未证明；随后下述4区取得独立真实TODO拒绝证据，余39区仍未由这些检查证明。只记录最终有效结果，不把预检、重复运行、参考测试或两次XA语义控制再加为编码区。

分布式4个真实服务区（DS-17/19/21/22）已在 `84781e8` 的[运行36776413515](https://github.com/weilhuang/backend-interview-labs/actions/runs/36776413515) 独立被真实TODO拒绝，两个参考模块也通过。但首个XA提交缺失控制的 `MultipleFailuresError` 序列化格式未被守卫接受，第二个控制未运行，所以整个8次调用门禁仍FAIL。修订后的归因器/消息夹具仍需新提交CI，当前新运行 `NOT_RUN`。只靠合同层不能判定XA持久化提交、Outbox发布标记以及Redis缓存填充/失效；`distributed_integration_audit.py` 的复现命令仍为：

```sh
python scripts/quality/distributed_integration_audit.py \
  --execute --xa-commit-controls --java-home "$JAVA_HOME" \
  --timeout 300 --total-timeout 900 \
  --work-dir build/quality/distributed-region-audit-new \
  --report build/quality/distributed-region-audit-new.json
```

两个参考模块先通过，随后4个TODO变体及可选2个提交缺失控制串行执行。每次新源码树、新编译和新鲜XML，失败必须归因到精确编码区/预期断言；编译、环境、容器、超时、skip或其他未知异常仍失败。默认只准备、退出2，明确 `NOT_RUN`；只有 `--execute` 完成全部计划运行才可能PASS。300秒单进程与900秒总执行预算涵盖语义控制及终止清理，没有并行容器放大或预算外重试。

适用平台仅针对作者工具：Linux CI Python3.12；macOS使用共享进程清理器需Python3.13或以上（`os.waitid` / `WNOWAIT`），不满足时在创建工作副本/启动Java前失败。普通学习者IDEA/Gradle流程不新增Python依赖。macOS原生运行未验证；这些脚本也不验证IDEA的Check、Reset、官方导出/导入。CI证据、时限与上传范围见[分层CI](../ci.md#分布式四区真实拒绝门禁)，最终计数与诊断边界见[阶段报告](中文阶段报告.md#补充审计37个合同区与四个真实服务区)。

## 6. 官方 ZIP 和原生导入产物只读比对

```sh
python scripts/quality/archive_contract.py \
  --course java-concurrency \
  --archive /path/to/official-export.zip \
  --imported-dir /path/to/untouched-native-import \
  --report build/quality/archive-contract.json
```

该脚本只读取真实 ZIP，不生成/修改官方归档。检查观察到的 v23 格式、题目集合、全部公开资产、题面、可见性、经过替换后重新偏移的 UTF-16 占位区与非空答案载荷。未知格式明确失败。

**原生 ZIP 的 contents 是插件加密载荷，不能直接与作者明文比较。** 脚本不会解密，也不将非空载荷声称为正确明文。可选 `--imported-dir` 指向已经由插件干净导入且未作答的目录，才会逐字比较所有任务学员起点和附加资产。它只读取已有导入结果，不声称自己执行了原生导入。`gradlew`、`gradlew.bat`、Wrapper JAR 在本次官方导出中不被打入，原生导入器负责生成；此脚本不证明生成行为。

C02并发测试修订前，本轮 C00/C01、C02、C03 共31题的全部归档元数据及原生干净导入明文比对通过。修订公开测试后，原C02归档保持不变，严格比对当前源码会准确报该测试文件不一致；新测试仍需新版官方导出及原生回归，不能借用旧包结果。试点 0.2.0 官方 ZIP 与当前作者清单比较发现缺少附加 `阶段报告.md`，任务结构与占位检查已通过，但严格资产契约为 FAIL，不能静默标绿或改写已交付 ZIP。这个文档差异不等于12题判题代码失败。

## 7. 原生 IDE 自动化的可选后续

[IntelliJ 官方 Starter/Driver](https://plugins.jetbrains.com/docs/intellij/integration-tests-intro.html) 是可行的开发基础：Starter 管理独立 IDE 生命周期，Driver 负责 UI/API 交互；它是通用插件测试框架，UI 部分仍可能变动，并非现成 Academy 验收工具。官方示例还说明 IDE 进程异常并不自动使测试失败，CI 必须把异常收集映射到 JUnit 失败。[UI 测试文档](https://plugins.jetbrains.com/docs/intellij/integration-tests-ui.html)说明了 UI 定位方法。

最小可选实验应另设工程和独立测试进程，固定 IDEA 261 系列/Academy 版本及下载摘要，不复用当前工作中的 IDE 配置、系统目录或项目；不装持久远控、不公开控制端口、不自动信任任意工程、不关闭浏览器/IDE沙箱或 TLS。先只验证启动、等待索引、打开一份无秘密的测试课程、收集异常并正常关闭，确认依赖与许可条件后才扩展完整流程。本轮没有安装或运行这个框架，也没有把未验证的伪代码当成可执行 CI。

当前最可靠的发行补充仍是官方 IDE 操作清单：

1. 作者副本中运行 Check All Tasks，记录总题数和零失败通知；导出时不可选 Create anyway 掩盖失败
2. 官方导出后，记录 ZIP SHA-256、准确 IDEA/插件/JDK 版本
3. 两个全新位置原生导入；比对每题顺序、占位、辅助资产及全部公开测试/答案
4. 每题实际 Check：起点失败 → 填入参考解通过 → Reset → 再次 Check 失败；保留每题结果及错误日志
5. 检查中文/提示/ASCII/长答案渲染、滚动、源码导航与调用端运行；这部分不能由静态文本或 JUnit 代替

已完成的代表题 GUI 结果和未覆盖项仍以[界面验收报告](../界面验收报告.md)为准；本文件不会扩大已有 GUI 验收范围。
