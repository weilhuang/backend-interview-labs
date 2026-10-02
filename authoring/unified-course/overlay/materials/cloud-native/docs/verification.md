# 如何读源码和验证

本草稿提供脚本，当前没有执行Java、Docker或Academy原生Check。以下命令说明脚本的用法，不表示对应运行阶段已经通过。

## 1. 只需Python的离线检查

在本包根目录运行：

```sh
python3 course/materials/cloud-native/bin/verify_offline.py
```

入口会拒绝零测试选择。测试覆盖配置隔离、验证器异常分类、旧证据/旧class检查以及合成进程的shell信号行为；不会启动真实Java或Docker。RESP假服务和合成class字节只用于测试验证器，不证明真实Redis/Lua或JVM通过。

## 2. JDK21原生验证（当前NOT_RUN）

使用Java 21，输出目录必须不存在；脚本不删除或覆盖旧class。每次重试用一个新的目录和新的结果文件。

```sh
CLOUDNATIVE_CLASSES=./local-runs/run-001/classes sh course/materials/cloud-native/bin/compile.sh
python3 course/materials/cloud-native/tests/native_verify.py --classes ./local-runs/run-001/classes --evidence ./local-runs/run-001/native.json
python3 course/materials/cloud-native/tests/variant_verify.py --evidence ./local-runs/run-001/policies.json
```

编译产物带输入与class哈希记录。源码变化、多出旧class、缺少记录、已存在结果文件都会明确失败，不能把其他运行的结果作为本次结果。原生HTTP测试使用RESP假服务，不执行Redis Lua。

## 3. 真实Docker验证（当前NOT_RUN）

`tests/docker_verify.py`和`tests/docker_variant_verify.py`是供统一环境入口调用的模块，不是已经可用的C11启动命令。环境适配完成前，不应自行拼装总课程命令。

统一调用方必须提供：经过预检的回环端口、唯一版本台账、专属verify项目、新namespace和空证据目录。缺Docker时返回NOT_RUN；调用方必须以非成功状态展示，不能切换mock后报完成。

正确入口与错误解都要真正构建并执行业务断言。只有指定的业务/镜像/信号违约能证明相应错误解被杀死；拉取失败、编译失败、命令异常、日志缺失或主机太慢不算成功反例。

HTTP错误解的失败名只是定位信息，评分还必须核对实际状态与响应字段。`wrong-ready`仅接受依赖可用且库存未初始化时的`200 READY, seeded=false`；`wrong-seed-reset`仅接受第二次初始化成功返回`200`、布尔`created`或整数库存违反幂等契约，且读取库存与响应一致。两者都要求目标请求前后的依赖及库存证据满足前提。

传输超时、断连、无效JSON、依赖DNS/CONNECT/AUTH/TIMEOUT/PROTOCOL以及非预期5xx单列为`INFRASTRUCTURE`。报告保留每次HTTP观测的状态、响应与分类；这些故障不会被错误解矩阵计为目标业务错误。

停止仅作用于本验证项目，并保留数据卷。脚本不执行全局prune、不删除用户卷、不调整socket权限，也不为调试开放公网管理端口。

## 4. Academy集成（当前NOT_RUN）

三课提供作者元数据和UTF-16占位范围。仍缺总课程JUnit桥、Gradle接线、strict locks，以及原生编辑区/Check执行验证。先完成这些依赖，再验证学习者初始失败、两种正确解通过及错误解失败；不能只靠命令行日志代替原生交互。
