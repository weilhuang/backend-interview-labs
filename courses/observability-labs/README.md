# C12 可观测性源代码草稿

当前状态：源文件已准备；Java编译、JUnit、HTTP服务、Collector/ELK/SkyWalking、原生Academy、新环境重建均为 **NOT_RUN**。本草稿不包含历史通过报告，不把静态结构检查当运行验收。

从[中文零基础入口](docs/00-从一次请求认识观测.md)开始，按结构化日志 → 低基数指标 → 跨服务传播学习。前端与调用方已提供，学生只补明确的方法。

## 结构

- observability-lab：12个Java主源码、6个公开测试类、Usage、前端和应用配置
- variants：双参考源码树（完整类对照范围见文档）、starter与8个错误变体；manifest中的expected是测试预期，不是执行结果
- academy-overlay：目标为唯一 courses/backend-interview 的3题候选结构，尚未合入或原生验收
- docs：中文术语、分步练习、提示/答案、源码路线、后端分层教程与阶段报告
- infra：Collector、Prometheus、ELK配置和合成fixture，仅候选
- validation：JDK21、Boot3.5.16的独立验证声明；完整依赖锁待重新解析冻结

## 测试入口（需在获准环境中实际执行）

显式设置已有JDK21的JAVA_HOME与Gradle8.10.2的GRADLE_HOME，运行 bash scripts/verify_java.sh clean test。双解/错误解使用 python scripts/verify_java_variants.py。这些命令没有在本轮执行，也不自动安装工具。

统一课程接入后使用唯一 bash scripts/gradle.sh 及 manifest/academy-overlay-proposal.json 中的原生项目名。图示使用课程内ASCII，另保留可编辑DOT源，不依赖缺失图片。

后端配置须先审核镜像并写入唯一台账，再运行真实校验。没有自行创建账号、使用真实凭证、改变安全设置、启动Docker或付费服务。

## 验证器边界

普通mock可验证脚本拒绝坏证据，不能代替运行Java/后端。r2验证器使用本次唯一构建目录、明确业务失败清单、严格链路语义和完整ELK采集范围。详见docs/06-参考实现范围与验证器契约.md。任务生成工具依赖requirements-authoring.txt中的固定PyYAML，不自动安装。
