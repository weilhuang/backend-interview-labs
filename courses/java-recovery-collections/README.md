# Java 编码恢复与集合原理 · Academy 作者课程 0.1.0

本包是完整 Java 后端面试课程体系的第一批 **12 个实际可执行任务**，不是把完整范围压缩成两周。覆盖 C00 编码恢复与 C01 集合的一部分；规划中的 16 个教学单元、JUC/JVM、Spring、数据库、缓存、MQ、分布式、云与可观测性和 Go 不因本包完成而视为完成。课程规划见仓库 docs；本目录才是 Academy course root。

## 先选择打开方式

### A. Academy 作者模式与正式学员预览

1. 使用 IntelliJ IDEA 2026.1.5 与兼容该 IDE 构建的 JetBrains Academy 插件（具体插件版本必须在实际环境验收记录中确认）。
2. 打开此目录，以作者身份打开课程。作者 src 保存参考实现，所以直接在这里跑测试应为绿色。
3. 使用 Course Creator 的 Create Course Preview 创建学员预览。占位区应显示 TODO，并由学员填写。实机菜单名称和导出步骤以所装插件为准。
4. **正式交付 Academy 学员包前**，必须在该精确 IDE/插件版本中完成：创建预览、逐题检查、错误代码触发失败、正确代码触发通过、导出 course archive、在干净位置重新导入。当前静态 YAML 校验和普通 Gradle 成功不能替代这一步。

本目录是作者源码课程，不是已验收的 Academy 学员归档。不得把普通 zip 重命名为课程归档。全部参考实现只在作者答案占位区或被排除的 authoring 目录；教师解题解析在仓库 instructor/java-pilot，位于 course root 之外。生成归档后还要检查答案是否泄漏。

### B. 不等待插件的普通 Gradle 学员副本

云端或其他开发环境都可运行，不依赖个人 Mac：

```sh
python -m pip install -r authoring/requirements.txt
python authoring/materialize_learner.py /absolute/path/to/new-java-pilot-learner
cd /absolute/path/to/new-java-pilot-learner
./gradlew test
```

目标必须是不存在且位于作者课程目录之外的路径。副本只有 TODO 实现、题面和测试；它是 **普通 Gradle 工程**，没有 course-info.yaml，也不是 Academy importer 的输入。未完成时 test 失败是预期行为。Gradle 可能首次下载固定版本的 distribution 和 Maven Central 依赖。

## 版本与编译边界

- Java 语言与 API 基线：17；Gradle JavaCompile 使用 `--release 17`
- 推荐完整 JDK：17 或21；Gradle/Test 实际运行在哪个 JDK 取决于 Gradle JVM / JAVA_HOME。本包没有静默下载或强制17 toolchain
- Gradle wrapper：8.10.2；distribution SHA-256 固定。launcher JAR 来自官方课程模板，出处见 THIRD_PARTY_NOTICES.md
- JUnit Jupiter：5.11.4；Platform：1.11.4
- OpenJDK 阅读基线：jdk-17+35，commit dfacda488bfbe2e11e8d607a6d08527710286982
- 现代 JDK21 专题将单独使用21基线；虚拟线程等内容没有塞进17课程里伪装兼容

为何先用17：对齐官方 Academy Java 模板的 JDK_17 环境，降低作者格式与基础 API 的变量；这不否定后续21实验，也不把本题 IntVector 当成 JDK ArrayList 完整实现。

## 学习顺序与验收

| 章节 | 任务 | 预计实作 |
|---|---|---:|
| 编码恢复 | 金额累计、ID解析、泛型有界栈 | 115分钟 |
| 集合契约 | 稳定去重、不可变Key、Top-K、快照、Iterator删除 | 220分钟 |
| 源码伴读 | 动态数组、HashMap索引与扩容 | 120分钟 |
| 综合实验 | LRU、近期ID去重窗口 | 125分钟 |

共约9小时40分实作估计，另留复盘、源码与二次无提示重写时间。不是必须一天做完，也不是整个面试准备的总工时。

每题有三阶提示、隐藏契约测试、可见 ExamplesTest、精确源码定位、实验输入及口述证据。建议：先独立写15–20分钟，按需展开一阶提示；运行单题；补边界；两分钟讲清不变量、复杂度与失败行为；隔日不看答案重写。

## 作者测试与维护

```sh
./gradlew test
./gradlew :java-pilot-01-recovery-01-money-total:test
python authoring/validate_course.py
python authoring/verify.py --junit-console /path/to/junit-platform-console-standalone-1.11.4.jar
```

verify.py 要求完整 JDK 的 javac，默认 `--release 17`。仅当精简环境没有 javac 启动器、但已有 jdk.compiler 模块时可显式加 `--java-module-compiler`；缺少 ct.sym 时另加 `--source-target-only` 会降为语言/字节码17验证，**不验证17 API兼容**。报告会记录此限制。

独立验证器运行同一套真正 JUnit5 测试：参考解通过；12个未修改学员实现全部拒绝；12个已知错误变体全部拒绝；每题另一个正确实现也应通过。它不修改作者代码，不等价于真实 Academy 检查器或 Gradle 集成测试。变体只是有限回归集，不是完整 mutation testing 分数。

编辑答案代码后必须重新计算 task-info.yaml 的 UTF-16 offset/length；格式化 Java 文件也可能使偏移失效。不要只手工移动源码而忘记占位区。validate_course.py 验证层级、文件、边界、重复键与构建配置引用，但没有调用 JetBrains 的实际 YAML importer。

## 运行超时与调试

每个 JUnit 测试以独立测试线程执行，3秒超时；Gradle 单任务另设60秒上限，防止错误循环拖住检查。独立验证脚本对子进程也设60秒上限，并实际验证一个死循环变体被报告为超时失败。依赖下载/首次构建耗时与题目执行超时分别处理。Gradle 调试连接时关闭 JUnit 超时，但默认60秒 Gradle 任务上限仍在。长时间断点调试使用 `./gradlew :java-pilot-01-recovery-01-money-total:test --debug-jvm -PdebugLab`，显式关闭任务上限；正常学习/CI不要设置该选项。若 IDE 直接运行 JUnit 调试，可设置 junit.jupiter.execution.timeout.mode=disabled_on_debug，或在调试后恢复测试超时。必要时使用 IDE Stop / Ctrl-C 结束运行。

## 状态

详见 authoring/VERIFICATION.md。未通过精确版本的 IDEA 学员预览及导出/重新导入前，发布状态始终是 author-mode pilot，不能标记正式学员包完成。
