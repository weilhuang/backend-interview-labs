# Java 后端面试实验室：统一课程 Draft

一个课程入口，15 个章节、100 个编码任务、159 个练习区。保留全部 84 道 V1 任务，接入 Docker/Compose/Kubernetes 基础、可观测性、Go 基础与快照、Go HTTP/Gin、身份策略扩展。源码、调用者、可见测试、分步提示、答案与图示都在同一课程中。

## 从当前题开始

1. 查看 [统一环境](docs/统一环境.md)，使用完整 JDK21、固定 Gradle 8.10.2；先运行 `bash scripts/lab.sh verify`
2. 查看 [逐题环境映射](docs/题目环境映射.md)，按实际课程路径执行 `bash scripts/lab.sh check <任务路径>`
3. Go 题还需要显式指定官方 Go 1.27.1 路径；HTTP/Gin 题需要预先准备并校验依赖缓存。检查不会隐式下载 Go 工具链
4. 作者正确实现由 Academy 占位投影成 learner starter；普通目录可运行 `python authoring/materialize_learner.py ../backend-interview-learner` 创建独立学习副本

## 验收范围

这是可复现的源码 Draft，不是已通过全部门禁的官方发行 ZIP。局部 Java/Go/HTTP 检查与完整基础设施、Academy 原生导入/Check/Reset 分开记录；本次公开组装没有重新执行 Java、Go 或 Docker。根 `fullCheck` 对尚未接入的扩展基础设施显式失败，不能用局部绿灯冒充整课通过。

- [Go HTTP 学习路线与边界](materials/go-http/学习路线与边界.md)
- [扩展学习与验收范围](docs/扩展学习与验收范围.md)
- [合并设计与验收](docs/合并设计与验收.md)

维护者应修改作者仓库中的九份 V1 真源或 `authoring/unified-course/overlay`，运行 `scripts/build_unified_course.py` 重建，不分别修改生成课程和作者源。
