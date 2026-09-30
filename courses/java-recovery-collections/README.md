# Java编码恢复与集合原理：内部教学模板试点

## 第一步：确认依赖和版本

- 必需完整 JDK21：`java -version` 和 `javac -version` 均应为21。IDE项目SDK与Gradle JVM也选21
- Gradle Wrapper8.10.2：仓库自带启动器，不需要另装Gradle。编译明确使用 `--release 21`
- JUnit Jupiter5.11.4 / Platform1.11.4：由Gradle从Maven Central解析
- Python3.11以上及PyYAML6.0.3：仅作者元数据、学员副本生成和质量回归脚本需要；普通Java学习不依赖Python
- IntelliJ IDEA2026.1.5与兼容其构建版本的JetBrains Academy插件：仅Academy界面学习/导出需要。具体插件版本仍须实机确认
- 固定源码：OpenJDK21 GA，tag `jdk-21+35`，commit `890adb6410dab4606a4f26a942aed02fb2f55387`。运行时更新补丁与GA源码不完全相同时须分别记录

```sh
java -version
javac -version
./gradlew --version
./gradlew test
./gradlew :java-pilot-01-recovery-01-money-total:run
```

这是 **12题内部试点**，用于验证后续课程模板与教学体验，不能称为V1。V1必须完整做好并验收Java、Java框架、分布式、数据库、消息队列五块；V2包含云原生、可观测性和企业级IAM/LDAP/Keycloak；Go待排期。课程规划见仓库 `docs/curriculum`。

本试点只用JDK和JUnit，不启动MySQL/Redis/Kafka。后续数据库与中间件课程统一使用仓库 `infra/versions.env` 和 `scripts/lab.sh`，不在每题复制一套版本常量或环境。开发和验证在云端进行，不依赖个人Mac。

## 第二步：选择学习工程

### Academy课程预览

1. 打开本目录作为作者课程。作者src保存标准实现，所以这里直接测试应通过
2. 在兼容插件中创建学员预览。实现区被替换为TODO，完整调用端与所有测试保持可见
3. 每题题面直接包含完整标准答案、中文解析、ASCII示意图、面试递进问题。答案无解锁门槛，不依赖隐藏教师目录，也不假设折叠渲染可用
4. 正式交付前仍必须验证精确IDE/插件组合、检查按钮、学员预览、导出、全新位置重新导入。静态YAML或普通Gradle通过不能替代这些步骤

本目录是作者源码课程，不是已验收的Academy学员归档。普通zip不能冒充插件生成的课程归档。导出检查要确认公开答案和测试完整保留，同时TODO实现区未被意外填成标准实现；答案公开是明确的教学要求，不是需要消除的泄漏。

### 普通Gradle学员副本

```sh
python -m pip install -r authoring/requirements.txt
python authoring/materialize_learner.py /absolute/path/to/new-java-pilot-learner
cd /absolute/path/to/new-java-pilot-learner
./gradlew :java-pilot-01-recovery-01-money-total:test
./gradlew :java-pilot-01-recovery-01-money-total:run
```

目标必须不存在且位于作者课程目录之外。副本的实现区为TODO，题面保留公开答案，调用端和全部测试可见。它没有course-info.yaml，是普通Gradle工程，不是Academy导入归档。未完成实现时测试和调用端失败属于预期行为。

## 完整工程结构

下面列出整个试点的顶层关系；每题题面另外列出该题的全部文件。所有模块都在同一个Gradle工程里，不能只复制某个Java文件后误以为拥有完整工程。

```text
java-recovery-collections/
+-- README.md                     学习入口与环境说明
+-- course-info.yaml              Academy课程配置
+-- build.gradle                  JDK21、JUnit、测试与真实调用端任务
+-- settings.gradle               12个独立任务模块
+-- gradle.properties             版本与构建参数
+-- gradlew / gradlew.bat          自带构建启动器
+-- gradle/wrapper/                固定分发地址、校验和、启动器JAR
+-- THIRD_PARTY_NOTICES.md         上游出处
+-- LICENSE-JetBrains-template    保留原始许可证
+-- .courseignore                 仅排除作者检查工具与构建产物
+-- .gitignore / .gitattributes    构建忽略项与固定换行
+-- java-pilot/
|   +-- section-info.yaml
|   +-- 01-recovery/              编码恢复
|   |   +-- 01-money-total/       PaidTotals
|   |   +-- 02-parse-ids/         IdParser
|   |   +-- 03-bounded-stack/     BoundedStack
|   +-- 02-collections/           集合契约
|   |   +-- 04-stable-dedup/      StableDedup
|   |   +-- 05-map-key/           TenantKey
|   |   +-- 06-top-words/         TopWords
|   |   +-- 07-snapshot/          Snapshots
|   |   +-- 08-safe-removal/      SafeRemoval
|   +-- 03-internals/             源码伴读
|   |   +-- 09-mini-array-list/   IntVector
|   |   +-- 10-hash-index/        HashIndex
|   +-- 04-capstone/              综合实验
|       +-- 11-lru-cache/         LruCache
|       +-- 12-recent-ids/        RecentIds
+-- authoring/                    作者质量工具，不是学员答案入口
    +-- manifest.json            源文件/调用端/正反变体清单
    +-- alternatives/            另一套正确实现，用于检查测试不过度限制风格
    +-- validate_course.py       元数据、公开测试、答案、UTF-16占位检查
    +-- verify.py                正反实现与实际调用端验证
    +-- materialize_learner.py    生成普通Gradle练习副本
    +-- requirements.txt         Python检查依赖
    +-- VERIFICATION.md          验证事实与未完成门槛
    +-- verification-report.json 机器可读结果
```

每个章节都有lesson-info.yaml；每题都有task.md、task-info.yaml、实现类、完整Usage类、完整契约Test类与ExamplesTest类。题面中的标准答案由该实现类生成，元数据检查会确保两者一致。

## 学习流程

每题遵循“读调用端与契约 → 自己实现 → 测试 → 运行真实调用端 → 改进 → 看源码机制 → 对照答案 → 面试口述”。完整测试53项加公开样例12项全部可读；不要删改契约测试来掩盖错误，可在ExamplesTest中继续增加自己的用例。

- 编码恢复3题：约115分钟
- 集合契约5题：约220分钟
- 源码伴读2题：约120分钟
- 综合实验2题：约125分钟

约9小时40分只是这12题的实作估计，源码研究、复盘及无提示重写另计，不能推导整个V1只需这些时间。两周是准备优先级约束，不是缩减完整质量或范围的许可。

## 作者质量回归

```sh
./gradlew test
python authoring/validate_course.py
python authoring/verify.py --junit-console /path/to/junit-platform-console-standalone-1.11.4.jar
```

验证器默认使用完整JDK21的javac和--release21。在精简环境中可显式指定--java-module-compiler；只有缺少ct.sym时才额外用--source-target-only，并明确它只是source/target21验证，不等于完整--release21验证。报告记录实际选项，不能把配置存在当作执行成功。

验证器要求参考解通过、12个替代正确解通过、12个未完成实现失败、12个错误变体失败，并执行12个真实调用端核对输出。另有一个故意死循环的超时检查。这是有限回归集，不是完整变异测试分数，也不形式化证明复杂度或并发安全。

编辑源文件或格式化代码会改变UTF-16占位偏移，必须同步元数据与题面标准答案。不得留下“源码已改、答案与占位区还是旧版本”的状态。

## 超时与调试

每项JUnit测试3秒，Gradle单任务60秒；独立验证子进程也有60秒上限。依赖下载与首次构建时间和单题执行超时分别处理。长断点调试使用：

```sh
./gradlew :java-pilot-01-recovery-01-money-total:test --debug-jvm -PdebugLab
```

-PdebugLab显式关闭Gradle任务时限，调试连接时JUnit时限也关闭；普通学习和CI不要设置它。IDE直接运行JUnit调试可设置junit.jupiter.execution.timeout.mode=disabled_on_debug。必要时使用停止按钮或Ctrl-C。

## 当前状态

见authoring/VERIFICATION.md。本包始终标记为内部教学模板试点，既不代表完整V1完成，也不代表Academy学员归档已经验收。
