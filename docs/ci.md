# CI：验收范围、成本与证据

## 当前策略

统一入口为 [课程分层验收](../.github/workflows/ci.yml)，九个原课程工作流改为 `workflow_call`。原有真实 Gradle/JUnit、错误变体、真实数据库/broker、RPC、恢复和浏览器测试命令保留；Gradle 显式关闭构建输出缓存。此调整没有增加定时运行、付费 runner、写权限、凭据或仓库设置。

**质量优先：不跨运行复用“通过”结果，不把未运行写成通过。** 历史报告只供审查，不参与新提交的放行判断。没有跨运行证据缓存、TTL、自动续期或历史状态 API。

### 每次都执行的轻量层

1. CI 路径映射、Git 差异边界、总门禁和工作流约束自测
2. 共享环境脚本无 Docker 回归、完整 JDK21 台账读取器测试、镜像快照漂移与 shell 语法检查
3. 仓库 Markdown 本地文件链接、中文标题锚点、引用式链接检查
4. 十门作者课程的通用元数据/占位/资源检查，以及各课程**原有**静态约束（7 个 `validate_course.py` 和 3 个 `verify.py` 的 `validate()`）
5. 课程库存检查：新增/删除 `course-info.yaml` 必须同步配置真实验收和旧静态入口，不能仅让九个旧套件通过就声称新课被测

旧静态约束包括必需教学标题与标准答案等；修改 `task.md` 仍执行这些原有检查。静态层不启动 Docker、Gradle 或 IDEA。它使用 JDK21 编译小型台账探针，因此仍需 `setup-java`。

本地链接检查不请求所有第三方网站，报告明确写 `external_http_reachability=NOT_RUN`。静态元数据也不能代表官方 IDEA/Academy 导入、Check All Tasks、重置或学习者实际操作通过。

## 真实验收如何选择

PR 使用 `merge-base(base.sha, head.sha)` 到 `head.sha` 的**累计差异**，并在 GitHub 的当前 PR merge checkout 上测试。PR 的 `edited` 事件也重算范围，覆盖更换 base 分支；因此仅修改 PR 标题/正文也会重新验证累计范围。不是只比较 `synchronize.before` 与本次 head：后者会让一次文档补丁盖掉 PR 中仍然存在的失败代码。

| 变更位置 | 真实套件 |
| --- | --- |
| `courses/java-recovery-collections/` | java-pilot、lab-environment（共享镜像还会构建试点） |
| `courses/java-foundations/` | java-foundations |
| `courses/java-concurrency/`、`courses/java-jvm/` | java-advanced |
| `courses/java-frameworks/` | java-frameworks（后端与 UI） |
| `courses/data-storage/` | data-storage（MySQL 与 Redis） |
| `courses/messaging/` | messaging |
| `courses/distributed-systems/` | distributed |
| `courses/backend-capstone/` | backend-capstone |
| `infra/` 的非 Markdown 文件 | frameworks、data-storage、messaging、distributed、capstone、lab-environment |
| 台账生成器及其测试 | frameworks、data-storage、lab-environment |
| 已显式登记的共享实验脚本及其测试 | lab-environment |
| 单个课程 workflow | 该套件 |
| CI 调度脚本、统一 workflow、`scripts/quality/` 判题器、未知共享脚本/配置/新课代码 | 全部九套（新课还必须通过库存检查） |
| 仅 Markdown 的变更 | 完整轻量层，不冒称真实服务测试已跑 |

删除、重命名会同时检查受影响路径；脚本、锁文件、Gradle Wrapper、课程 YAML 元数据、版本台账都不是文档免测项。diff 无法取得时保守全量。

### “文档-only”的确切边界

- 一个**整个 PR 累计差异都只有文档**的变更，不运行重型服务
- 若一个大 PR 已经包含九个模块代码，后来只提交文档，该 PR 仍需验收九个模块。这是防止旧失败被新 skipped 状态掩盖的保守选择
- 当前大 Draft PR 的九套重跑不会仅因本次改造消失；不能据此宣称已节省某个具体百分比或金额。后续小范围 PR、真正文档 PR、依赖缓存与过时运行取消才产生可确定的成本改善
- `main` 每次 push 都是独立的全量基线，即使该 push 仅修改文档也全量；发布完整性优先于这部分节省

## 新增学员源码夹具三阶段门禁

每个课程只增加一次 `academy_gate.py roundtrip` 调用，使用已有 runner、JDK、下载缓存与真实 Docker 能力。按该课学习区需要的最低判题层选择，不强迫没有集成拒绝契约的纯单测题依赖 Docker 失败：

- **contract（8 课）**：试点、基础与集合、JUC、JVM、Java frameworks、messaging、distributed-systems、backend-capstone
- **integration（2 课）**：MySQL、Redis；Redis 04/05/06 空实现可能通过纯 contract，必须由真实 Redis/MySQL 集成拒绝，不能把纯单测绿当学习者判题成功

每课的一次命令完成：干净学习者空解被对应测试拒绝 → 标准解全部通过 → 第二次从源码夹具生成的空解再次被拒绝。参考解、全部选中任务的 JUnit XML、失败归因和非零测试数量都须符合门禁，不把启动/依赖/容器异常作为“预期学员失败”。

这 8 课的 contract 门禁不等于完成三倍真实 broker/数据库测试；它们原先的正确解真实 Docker、网络、恢复与 UI 验证全部继续执行。共享 `lab-environment` 不再次重复试点课程的三阶段命令。夹具 ZIP 是仓库源码测试夹具，**不是**官方 Academy 导出包或原生 Reset UI 证明。

每 phase 超时上限 600 秒，整 gate step 上限 35 分钟。三个纯 Java 工作流及 framework 后端 job 上限 45 分钟，distributed 与 C14 为 50 分钟，MySQL、Redis 与 MQ 为 60 分钟；独立 UI 与共享环境任务维持原上限。这个预算覆盖已观测原流程、35 分钟 gate 和上传余量，不要求跑满。卡死必须超时失败，保留日志后根据实测再判断，不能无限等待或自动拉高上限。

上传保留 root JSON、逐 phase 日志、源码 manifest 和尚存的 JUnit XML，不上传整个夹具构建目录。报告从 `build/quality/` 上传到 artifact，**不会加入任何依赖缓存**。每次干净工作目录都重新构建，不借测试输出缓存充数。

### 已有成本基线和新增成本

针对提交 [1fb27d8885bf1eb62b112d2e15f5478becf697fa](https://github.com/weilhuang/backend-interview-labs/commit/1fb27d8885bf1eb62b112d2e15f5478becf697fa) 的九个成功工作流，读取 GitHub jobs 开始/完成时间得到十二个 job 累计 **3634 秒，约 60.6 runner 分钟**；并行墙钟约 15 分钟。这不是账户账单或剩余额度，不包含 GitHub 计费取整。

原始逐 job 秒数为：基础 233、C14 538、framework UI 90 / backend 311、infra 325、pilot 90、MQ 888、distributed 470、MySQL 183、Redis 176、JUC 180、JVM 150。MySQL 原真实测试步骤约 172 秒、Redis 约 163 秒，是首轮采用每 phase 600 秒而非更大上限的依据。

新增三阶段门禁会增加实际 runner 分钟，须等新目标 SHA 的首次完整 CI 后重新量化。当前大 PR 不承诺因一次文档提交省掉九套；取消过时 PR 运行和只缓存依赖也不能拿估算冒充已发生的账单节省。

## 同仓 PR 与 fork PR

两者使用同一个累计差异规则和 merge checkout，没有跨分支/跨 fork 结果复用。入口是 `pull_request`，不使用高权限的 `pull_request_target`，不继承 secrets。所有 checkout 都设置 `persist-credentials: false`；工作流仅声明 `contents: read`。

fork 是否需要人工批准运行、私有仓库是否允许 fork Actions，由现有 GitHub 设置决定，本次不修改这些设置。缺少批准、merge 冲突、runner 不可用都不等于通过。

## 全量入口（包括尚未合并的 Draft）

- 给 PR 加 `ci:full` 标签会触发全量；**标签保留期间后续提交也继续全量**，避免一次全量失败被后续文档变更盖掉。确认全量成功后可由维护者移除标签，恢复累计路径选择。工作流不自行增删标签
- 当前 Draft 首次引入 `ci.yml` / `scripts/ci/` 的提交本身就匹配全部套件，可以直接用 PR 的自动运行建立全量结果
- 默认分支已有入口后，可在 Actions → 课程分层验收 → Run workflow 选择目标分支进行全量。新 workflow 尚未存在于默认分支时，**不假设按钮可用**；Draft 用上述 PR 入口。GitHub 官方对按钮/dispatch 的默认分支条件见下方来源
- `release: published` 对该发布引用强制全量，适用于发布与预发布；它是发布后的检查，不会自动撤销发布。发布前应先对候选 SHA 手动全量

所有全量入口都实际执行九套，不读取旧“通过”来跳过。`workflow_dispatch` 是独立运行，并不替代 PR 的 required checks；PR 是否可合并仍检查其对应 PR 运行与仓库规则。新课程需扩充映射、工作流与旧静态门禁，而不是只增加一个名字。

## 取消、缓存与报告

### 取消过时运行

同一 PR 的新事件可取消旧运行。当前订阅 `labeled`，添加任意标签（不只是 `ci:full`）都会重验累计范围并替换同 PR 的旧运行；这项保守行为会带来额外成本，不使用 job 级跳过来伪造新绿勾。移除标签不会单独触发 `labeled`，下一次 PR 事件按当时标签重新计算。不同 PR 使用不同并发组；main、手动、发布运行使用独立 run ID，不互相取消。取消会保留 GitHub 的 `cancelled` 状态，绝不是通过。

各课程保留 `if: always()` 的报告和清理步骤。但整个 runner 被取消/终止时，不能保证所有清理或 artifact 上传完成；日志/报告缺失必须如实说明，不能称“完整证据已保存”。GitHub 托管 runner 仍是一次性的。

### 只缓存下载依赖

Gradle 缓存仅覆盖 `caches/modules-2` 与 Wrapper 分发，不缓存编译输出、任务结果、课程 `build/` 报告、Docker 数据卷或容器。frameworks 使用自定义 `GRADLE_USER_HOME`，仅缓存该目录中对应的两类下载路径。

缓存键包含 OS、JDK21、套件、job 和 Gradle/Wrapper/锁文件摘要；恢复后仍执行所有选中真实测试。缓存 miss、过期或被逐出只影响下载速度。Python 轻量依赖缓存使用固定 requirements。缓存不能作为测试通过证据。

### 总门禁和可审查输出

`CI验收总门禁` 是统一汇总检查：

- `passed`：此工作流中要求执行的真实套件成功
- `not-run`：本 PR 累计范围未要求此套件，**未运行，不是通过**
- `failure`、`cancelled`、`skipped`、`missing`：如果计划要求该套件执行，总门禁失败
- 静态层或计划失败、suite 缺项/未知项，也不能通过总门禁

“Re-run failed jobs”可以保留**同一 workflow run、同一提交**已经成功的任务；汇总不声称这些任务在新的 attempt 重新执行，也不产生可跨运行复用的凭证。需要所有任务重新执行时使用 Re-run all jobs 或全量入口。

计划、静态报告、汇总 JSON 与原真实测试报告保留 7 天。真实套件找不到任何报告文件时，artifact 上传步骤失败；不能只靠空目录显示绿勾。所有报告名称包含 run ID 与 attempt；重试不会覆盖之前的失败证据，也不会与先前 attempt 的同名 artifact 冲突。

本次没有修改 branch protection/rulesets。若仓库已有旧 workflow 检查名的必需状态规则，迁移前需核实其名称；不要未经授权修改规则，也不要把永远 skipped 的检查设成唯一门禁。

## 本地检查

```sh
export JAVA_HOME=/path/to/jdk-21
export PATH="$JAVA_HOME/bin:$PATH"
python -m pip install -r scripts/quality/requirements.txt
python -m unittest discover -s scripts/ci/tests -v
python -m unittest discover -s scripts/tests -v
python -m unittest discover -s scripts/quality/tests -v
python scripts/ci/plan.py --check-inventory
python scripts/ci/validate_docs.py
python scripts/sync_course_versions.py --check
python scripts/quality/academy_gate.py metadata --report build/quality/academy-metadata.json
python scripts/quality/academy_gate.py legacy-metadata --report build/quality/academy-legacy-metadata.json
```

以上为静态与调度验证，不替代选中真实课程工作流，更不替代官方 IDEA 学习流程验收。发布前需检查**目标 SHA**的实际 Actions 结果。

## 官方依据

- [GitHub workflow 语法与路径差异语义](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax)：PR 路径过滤采用累计三点比较；被路径过滤跳过的必需检查可能 pending，因此统一入口不设 paths 过滤
- [工作流触发事件](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows)：PR merge checkout、fork 与 workflow_dispatch 条件、release 活动类型
- [可复用工作流](https://docs.github.com/en/actions/how-tos/reuse-automations/reuse-workflows)：同仓 `./.github/workflows/…` 来自调用者同一提交，权限只能保持或降低
- [并发控制](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/control-workflow-concurrency)：同组的取消/排队行为
- [Actions 官方依赖缓存](https://github.com/actions/cache)：缓存下载依赖与恢复键
- [重新运行工作流与任务](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/re-run-workflows-and-jobs)：重跑全部、失败或具体任务的区别

## 首轮新增门禁的实际运行（2026-09-30 UTC）

[提交 b79832d 的运行 36759817251](https://github.com/weilhuang/backend-interview-labs/actions/runs/36759817251) 已完成：

- 12 个实际测试 job 中 10 个通过、2 个失败；规划和静态检查通过，最终总门禁正确失败
- MySQL 原真实测试通过，新学员门禁发现死锁课的集成用例未调用学习者重试策略；这是真实覆盖缺口
- Kafka 的三副本测试在主题创建后的第一次元数据查询碰到暂态不可见，尚未进入 ISR 就绪等待；这是测试同步缺陷
- 其余八个课程工程的新三阶段门禁均通过；消息课程三阶段尚未运行，不能借用旧提交的通过结果
- 工作流墙钟用时 16 分 29 秒；按全部 job 的实际开始/完成时间累计为 **87 分 59 秒 runner 执行时间**

这些是 GitHub 返回的执行时刻，**不是账单、计费取整后的分钟数或账户剩余额度**。这轮两个失败也让后续步骤未执行，所以 87 分 59 秒不能当作完整成功验收的固定成本。新增课程判题验证会增加实际运行量；同一大 PR 的累计代码范围仍覆盖所有模块，不会把一次文档提交伪装成整个 PR 无须验证。

本轮没有预算、付费 runner、仓库可见性或计划任务改动。后续修复须用新提交重跑，历史红色结果保留为可复核证据。
