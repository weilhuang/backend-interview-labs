# 阶段报告：共享 Docker 实验环境基础

日期：2026-09-30。范围：共享基础环境、命令入口、版本同源、CI 基础验收；不包含尚未实现的后端项目课程或前端页面。

## 一、这一阶段完成了什么

交付了最小可用的环境基础代码：MySQL + Redis 默认组合、可选单节点 Kafka、一次性完整 JDK21 构建容器，以及统一版本读取。目标是让不同课程共用同一组镜像，并让低磁盘/低性能学习设备只启动眼前需要的组件。

当前已完成**代码、离线测试及 Linux amd64 云端 CI 基础验收**。制作环境本身无 Docker，但独立 GitHub Actions runner 已运行真实 MySQL/Redis/Kafka 与 JDK21 构建；Mac/arm64、宿主应用及 Testcontainers 项目集成仍需后续验收。

## 二、结构与职责

```text
infra/
+-- versions.env                 唯一机器可读镜像版本台账
+-- compose.yaml                 MySQL / Redis / Kafka / JDK21构建
+-- .env.example                 回环地址实验参数与非生产示例密码
+-- testcontainers/LabImages.java 未来项目课测试读取同一台账
scripts/
+-- lab.sh / lab.py               中文统一入口与安全检查
+-- ci_smoke.py                   CI独立项目中的真实读写/消息收发
+-- tests/                       无Docker回归
.github/workflows/
+-- lab-environment.yml          顺序执行真实组件/构建验收
```

文档：[使用说明与资源预算](README.md)、[预置前端与课程接入契约](runtime-contract.md)、[官方来源和逐项验证记录](verification.md)。

## 三、具体设计与可复制示例

### 1. 小环境优先

```bash
./scripts/lab.sh doctor
./scripts/lab.sh up                 # 只开 MySQL + Redis，并等待健康
./scripts/lab.sh check core
./scripts/lab.sh down               # 所有本项目组件停机，数据/缓存保留

./scripts/lab.sh up kafka           # 独立消息队列实验，不同时开全栈
./scripts/lab.sh check kafka
./scripts/lab.sh logs kafka
./scripts/lab.sh down
```

每个长期服务都有协议级健康检查、内存/CPU/日志边界。所有发布端口绑定 `127.0.0.1`；入口要求 Engine28.0+，原因是官方披露更旧版本存在同网段访问回环发布端口的风险。未使用特权容器、宿主网络、Docker socket 或自动公网开放。

### 2. Java21 构建与缓存

```bash
./scripts/lab.sh build . javac -version
./scripts/lab.sh build courses/java-recovery-collections bash ./gradlew --no-daemon test
```

复用 Gradle/Maven 缓存卷；仍由课程自己的 Wrapper 决定 Gradle 版本。基础构建容器不具备嵌套 Docker/Testcontainers 访问权，不为跑测试自动挂载宿主 socket。未来集成测试在有完整 JDK21 和受控 Docker daemon 的云环境运行。

### 3. 版本与数据隔离

Compose 与未来 Testcontainers 都读取 `infra/versions.env`，避免多个课程选不同镜像别名导致重复拉取。Maven/JDK 已锁官方多架构 index digest；其他选定镜像目前锁完整补丁标签，正式发布前继续核验 registry 摘要。共享镜像不等于共享测试数据；集成测试应使用独立临时容器和随机端口。

默认 `down` 不删除卷；只有精确指定 `reset --confirm-reset 项目名` 才删除该项目数据与缓存。脚本不会执行全局 prune，不会因为启动失败而自动重置。

### 4. 前端交付边界

后续 Web 项目课由作者交付已构建、已集成的前端，学习者不需自己接页面、装 Node 或改代理。契约要求真实业务页面、前后端版本匹配、readiness 与完整业务链验证。当前 Java 集合首包无 Web 页面需求，本阶段没有用一个通用空壳冒充未来前端项目。

## 四、已测试 / 尚未测试

| 阶段 | 当前结果 | 证据含义 |
| --- | --- | --- |
| Python 无 Docker 回归 | 42/42 通过 | 配置边界、命令组合、错误处理、数据保护、CI 隔离和脱敏逻辑 |
| 静态环境校验 | 通过 | 固定镜像、回环端口、健康/资源边界，无特权/socket |
| Bash/Python 语法 | 通过 | 不代表 macOS 或容器运行已验证 |
| Java 共享版本读取器 | 完整 JDK21.0.12.1+1 实际编译与读取通过 | 仓库根/课程子目录都能读取；未知键/缺失台账会失败，不是容器集成测试 |
| 云端 CI | 通过 | run 36708893556；实际 Engine28.0.4/Compose2.38.2、Linux x86_64 |
| 当前云 Docker doctor | 失败，缺 CLI | 明确阻塞；未擅自安装 daemon |
| Compose 真实解析/拉取/启动 | 通过 | 精确提交的云端 CI |
| 真实 MySQL/Redis 读写与持久化 | 通过 | 写入→读取→down/up→再读取均成功 |
| 真实 Kafka 收发 | 通过 | 建主题→发送→读取并比对内容成功 |
| JDK21 镜像内 Gradle 构建 | 通过 | 真实容器内 BUILD SUCCESSFUL |
| Testcontainers 与 Mac 双架构 | 未执行 | 上游架构证据不代替实测 |

本地无 Docker 的复核命令：

```bash
python3 -m unittest discover -s scripts/tests -v
./scripts/lab.sh verify
bash -n scripts/lab.sh
python3 -m py_compile scripts/lab.py scripts/ci_smoke.py scripts/tests/*.py
```

## 五、如何确认“真实可用”

云端 CI 必须在精确提交上产生成功记录，不能只看 `config` 或容器进程启动。先保留各阶段日志，再验证：

1. core 的实验账户成功创建表、写入/读取标记，Redis 写入/读取同一标记
2. `down` 后重启，两种存储都能读回原标记
3. Kafka 单独运行，建主题、发送标记并消费到完全一致的内容
4. 使用台账中的完整 JDK21 镜像执行 `javac -version` 和首包 Gradle 测试
5. 记录实际 Engine/Compose/镜像/CPU 架构；失败需要修复后重跑，拉取失败不能算代码通过
6. CI 无论成功失败均保留脱敏日志；只清理由本次运行号限定的一次性项目，不删除学习者已有卷

[本次真实 CI 运行](https://github.com/weilhuang/backend-interview-labs/actions/runs/36708893556) 对应提交 `a57a95b67a0d29cd280a54d3f761c340b9cad0d4`；精确平台、时间和仍未覆盖项目见[验证记录](verification.md)。

## 六、建议重点 Review

- 共享台账是否真正被所有课程复用；新增课程有没有又写了一份版本常量
- `up` 的服务选择与 `down/reset` 的项目边界，尤其是失败不能误删教学数据
- MySQL/Redis 凭据是否仅用于实验；日志上传前是否脱敏；镜像更新是否做了数据兼容检查
- Kafka 的宿主/容器双监听地址、命名卷权限及首次运行情况
- Java 构建容器的真实完整 JDK、Gradle Wrapper、缓存复用与 Linux 输出文件所有权
- 后续项目课是否真的附带可用前端并验收业务链，而不是仅提供接口清单
- 未测试项是否持续明确标注，尤其 Mac arm64/x86、Testcontainers 和真实 CI 结果
