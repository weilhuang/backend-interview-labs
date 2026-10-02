# C12 可观测性教学候选

2026-10-02 本地完整 Temurin JDK21 + Gradle8.10.2 实测通过：当前主源码和双参考各28项公开测试；8个错解与4种starter均编译成功，并命中冻结的精确预期失败集合。15个scenario共167次方法执行，其中115次通过、52次预期业务失败，零意外失败、零跳过。详见[中文阶段报告](docs/阶段报告.md)。

新加入的C12 Actions工作流尚未运行。Docker、真实Collector、ELK、SkyWalking及原生Academy GUI仍为NOT_RUN；两个真实HTTP服务是在同一测试JVM中的两个独立Spring context，SDK内存exporter不是Collector集成。

从[零基础入口](docs/00-从一次请求认识观测.md)开始，按结构化日志 → 低基数指标 → 跨服务传播学习。前端和调用方已提供，学生只补明确方法。

## 结构

- observability-lab：12个Java主源码、6个公开测试类、Usage、前端和配置
- variants：双参考、starter和8个错解；manifest中的expected是测试契约
- academy-overlay：3题候选结构，尚未合入唯一课程根或完成原生验收
- validation：JDK21、Boot3.5.16与本轮重新解析的新gradle.lockfile
- docs与infra：中文讲义、ASCII调用链、后端候选配置与真实校验入口

## 本地运行

设置完整JDK21的JAVA_HOME与Gradle8.10.2的GRADLE_HOME后，在本目录运行：

- bash scripts/verify_java.sh clean test --no-build-cache --rerun-tasks：当前主源码全部公开测试
- python scripts/verify_java_variants.py --manifest manifest/variants-extended.json：双参考、8错解、综合starter与3题starter的完整14变体矩阵

无需先运行生成器；变体和学员源码已提供。任务编写/重新生成才需要requirements-authoring.txt中的固定PyYAML。普通测试不使用 --write-locks；所有变体都以同一个validation项目构建并读取同一锁。该锁是重新解析的新锁，不是丢失旧锁的恢复。

专用 .github/workflows/observability-java.yml 在相关PR或main路径变更时运行当前主源码加完整14变体，保留本次XML、日志、源码与锁前后hash、receipt；不发布发行包。其首次远端结果仍待验证。

统一课程接入后再使用唯一 bash scripts/gradle.sh 及 manifest/academy-overlay-proposal.json 的原生项目名。后端配置仍须先确认唯一镜像台账，再单独实际验收。
