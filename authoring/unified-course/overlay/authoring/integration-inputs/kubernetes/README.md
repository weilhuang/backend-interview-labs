# 接入唯一Academy课程的提案

本候选没有course-info.yaml，也不生成第二个发行course。只将course/c11-cloud-native下04..06三课追加到总课程已有C11 section；不得覆盖原01..03 content，不修改旧97课。共享代码放同一个总课程的materials/kubernetes。

1. 总生成器用integration/task-map.json取准确映射；course学习者文件是可编辑starter，共享materials及每课answers为完整答案
2. academy-overlay只作为作者元数据候选：复制c11新增lesson子树，合并section content；共享材料仍取course唯一来源，overlay预览副本不重复导入
3. 原生task project名保持section-lesson-task；引入kubernetes-task.gradle并显式传kubernetesMaterialsDir绝对路径。source覆盖只发生在build/generated-kubernetes-src，不能写回共享答案
4. JDK21；新增模块显式JUnit Jupiter5.11.4，复用已存在课程版本惯例，不声称全仓统一JUnit版本。test workingDir=project.projectDir，task/material/python路径通过系统属性传入
5. rootTest必须包含这三课test。作者显式生成并审计每module dependency locks后启用STRICT；本候选不伪造lockfile，不运行--write-locks
6. 课文、练习、答案、test与共享src/test-java/tests/bin/web/manifests全部可见。additional-files.json列出待并入总course文件元数据的共享文件，不生成新的course-info
7. Check默认只执行可见Java合同与YAML合同，不偷偷启动Docker。真实Kind是按需显式运行，结果独立记录；没有Kind不得让Java/YAML绿灯宣称已过E2E
8. 首次native验收必须分别用正确答案、每个错误变体和INVALID_ENV情形观察IDE状态，确认失败向Academy传播。仅pytest/Python或命令行JUnit通过不构成native验收

版本台账提案只新增KIND_VERSION/KUBERNETES_VERSION/KUBECTL_VERSION/KIND_NODE_IMAGE；JAVA_BUILD_IMAGE、REDIS_IMAGE复用原key；JAVA_RUNTIME_IMAGE复用PR6提案。所有运行入口要求传总台账，versions.env.additions不能单独运行。
