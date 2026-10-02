# Go基础三课：独立源码候选

本目录保存C13-01、C13-02、C13-03三课的源码、中文讲义、完整调用方、可见测试和标准答案，尚未接入主Java Academy课程。不含course-info.yaml，不构成第二个已发布课程根。

## 从哪里开始

1. 阅读对应task.md：greeting（第一次Go构建测试和调试）→quantity（变量控制流与可靠输入）→order-total（结构体方法与值指针）
2. 命令行学习从learner-static/go-course/core/<任务>/go开始；这里的exercise.go是红灯starter。overlay保存作者源，不能把其中已有标准答案当自己的完成状态
3. 只修改练习区，先跑编译，再跑真实业务测试，再看完整main输出；每一步的命令、预期与排错都在讲义中
4. 完整标准答案和第二种实现位于各题go/answers；它们只需替换同一练习区，不要求改测试、import或调用方

三课均是“主Java课程里的可见Go源码+公开JUnit检查桥”的接入候选，不是原生Go Academy课程。Go编辑、断点调试及原生Check体验尚未验证。

## 内容与合同

- C13-01：Greeting处理中文名字、空白与空名字；读懂module/package/main/test
- C13-02：ParseQuantity把输入格式、整数溢出与1..1000业务范围分开，错误由errors.Is识别
- C13-03：Order.TotalCents使用整数分并检查乘加溢出，保持输入不变；先理解值接收者与切片共享，再学习快照所有权

订单的“逐行首错”是本实验API约定，不是通用企业标准。三条组合测试分别覆盖乘法溢出在先、加法溢出在先、非法字段在先；全量预校验之后才计算的错解会违反此约定。

每题提供两种正确实现、常见错解、Java对照、H1–H4提示、面试递进问题、ASCII调用图和PNG/SVG图示。测试定义包括45个表驱动子例、6个main进程子例、14个顶层测试；这些是定义清单，不是已执行结果，也不能相加当独立业务案例数。

## 工具链与运行状态

固定Go 1.27.1，无外部Go库。仓库不携带或自动下载SDK；GO_EXECUTABLE必须指向真实Go编译器的完整路径，缺失或版本不符应明确INVALID_ENV。

当前Go test/vet/race、独立JUnit、主课程Gradle、原生Academy及Actions均待执行。本提交保存源码，不以提交成功代替课程验收。每次实际执行后的日志应作为单独证据，不能用旧结果证明变化后的源码。

准备已有Python3/PyYAML可运行：

```sh
python scripts/test_static.py
```

准备官方Go 1.27.1并设置GO_EXECUTABLE后可运行：

```sh
python scripts/verify.py
```

此入口将分别验证starter构建成功/业务失败、双正确答案test/vet/race十次/main、错解业务失败、漏main反例及冷缓存重建。超时或编译失败不能冒充业务反例被拒绝。race依赖平台已有C工具链；不支持时记录NOT_RUN及原因，不伪装通过。

独立JUnit验证需JDK21和JUnit Platform Console Standalone 1.11.4，并设置JAVA_HOME、JUNIT_CONSOLE_JAR、GO_EXECUTABLE：

```sh
python scripts/verify_java.py
```

复验入口只在本目录work/evidence创建工作副本与日志，不修改作者源，也不会安装软件或下载依赖。

## 后续主课程接入

integration/是显式settings及独立Gradle adapter提案，不会自动应用。正式接入还需主课程生成器、课程顺序、白名单、锁文件、导出与原生交互共同验收。

三个新增task/三个占位仅作为下一版本提案；V1精确84/136与V2首片92/144保持，未来合并后的95/147不得通过修改旧基线来伪造验收。
