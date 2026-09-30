# Java框架工程与源码

本课对应完整课程C04与C05，采用真实Spring Boot与Spring项目，包含14个渐进阶段。它是完整V1中的框架部分，不代表全部V1已经完成。

## 前置环境与固定版本

| 项目 | 本课基线 |
|---|---|
| JDK | 完整JDK21；云端验证使用Temurin 21.0.12.1+1，编译release21 |
| 构建 | Gradle Wrapper 8.10.2；保留分发校验和 |
| 框架 | Spring Boot 3.5.16、Spring Framework 6.2.19，按Boot BOM解析 |
| 测试 | JUnit Jupiter 5.12.2、Spring Boot Test 3.5.16，全部测试公开 |
| 数据库 | 无Docker基础阶段使用H2 2.3.232；只证明相应Spring/JDBC合同 |
| 真实数据库 | 共享MYSQL_IMAGE当前为mysql:8.4.7；测试读取根infra/versions.env或其自动生成且带SHA256的shared快照 |
| Testcontainers | 统一1.20.6；用独立强制BOM覆盖Boot BOM的默认版本 |
| 预置前端 | 原生HTML/CSS/JavaScript 0.1.0，由Boot直接提供；无需Node、npm或前端构建 |
| Docker | 普通学习与H2测试不需要；共享环境最低Engine28.0、Compose2.20，实际daemon验收另记 |
| IDE | 目标IntelliJ IDEA 2026.1.5＋兼容Academy；本课实际插件导入/检查另行验收 |

课程制作、编译、测试优先在云端进行；不需要把构建负担转移到用户Mac。学习端可在IDEA导入课程，具体运行/远程连接方式另选。真实执行状态见[中文阶段报告](中文阶段报告.md)。

## 学习路线与完整项目

每个阶段都是独立Gradle模块，包含完整src、可运行Usage调用方、全部test、资源、题面、渐进提示和公开标准解。默认作者工程是可运行标准解；学生起点由Academy占位机制或课程自己的副本工具生成。题目不会隐藏调用者和测试合同。

1. 01 配置绑定与启动校验
2. 02 HTTP合同、验证、错误和预置中文订单页
3. 03 JDBC事务与失败原子性
4. 04 单元、MVC切片、真实HTTP分层测试
5. 05 基础认证授权与CSRF
6. 06 生命周期、健康与优雅关闭
7. 07 中文前端到真实JDBC的完整服务
8. 08 教学最小容器与真实构造注入
9. 09 Bean定义、后处理与生命周期
10. 10 真实循环依赖支持边界
11. 11 JDK/类代理、拦截链与自调用
12. 12 事务代理、传播与自调用失效
13. 13 MVC参数解析、拦截与错误链
14. 14 自动配置、条件退让与轻量starter

## 开始练习

在本课程根目录打开工程，先确认java和javac均来自JDK21。

```bash
./gradlew :01-configuration:test
./gradlew :01-configuration:usage
./gradlew :02-http-contract:test
./gradlew :02-http-contract:run
```

第二阶段服务默认仅监听127.0.0.1:18084。打开同一开发环境的浏览器访问该地址；如果服务在远程环境，请使用该环境已有受控预览方式，不能擅自把端口公开到公网。用Ctrl+C停止。

全部基础测试：`./gradlew test`。每个模块的`:usage`都是完整调用方；`:run`用于交互服务或控制台演示。具体前端操作见[前端使用](docs/前端使用.md)。

真实MySQL集成必须显式启用，并先有Docker访问：

```bash
# 可选覆盖；完整仓库或自带shared快照的独立课程无需设置
# export LAB_SHARED_VERSIONS=/实际仓库路径/infra/versions.env
./gradlew :03-transactions:integrationTest
```

MySQL测试完整可见但独立放在integration-test源集，普通test不会编译/运行该源集；只有integrationTest才解析其Testcontainers依赖并执行。未运行不是MySQL通过；没有Docker或共享台账会清楚失败，不能静默换镜像或把H2当成MySQL。共享服务统一入口是仓库scripts/lab.sh，课程不复制镜像常量。

## 标准解与真实掌握

每节task.md直接提供全部练习区标准解和解释，完整文件也公开。建议先独立尝试，再看提示或标准解；之后以新边界/故障变式回测。测试绿色、读过源码与独立解释是不同状态。课程支持面试准备，不保证任何招聘结果。

源码固定版本、具体读取入口与迁移边界见[源码与版本](docs/源码与版本.md)。普通源码ZIP不是Academy原生归档；实际导出和干净导入需要插件验收。

## Linux云端启动脚本

`scripts/course.sh doctor`检查JDK；`start 02-http-contract`或`start 07-integrated-service`启动；`check`等待真实HTTP就绪；`stop`只停止本课程登记且归属匹配的进程。脚本当前按Linux云端编写；其他学习环境可直接运行Gradle的run任务并用Ctrl+C停止。开发验证可显式用LAB_GRADLE_BIN选择已安装的同版本Gradle，LAB_OFFLINE=1使用已验证依赖缓存，不更换版本。

## 进程管理与修复回归

`python3 scripts/test-process-control.py`只在临时目录启动本测试的受控子进程，检查随机实例token与PID身份、退出状态和幂等停止。脚本采用Linux/macOS共同的ps接口，Linux9项回归已通过；Mac尚未实际运行，不能据此宣称跨平台实测通过。旧版未保存token的服务需在原启动终端结束，新脚本不会冒险认领。C04-06现有6项测试包含超时/中断时取消排队Future，正常退出才报告资源清理完成。

## 独立课程镜像台账

已登记自动生成的shared快照、SHA256和读取器，独立课程无需父仓库。全部Gradle真实集成测试使用台账中的Ryuk与tiny辅助镜像。运行入口、显式覆盖、校验失败和Academy ZIP的Wrapper差异见[独立课程镜像台账](shared/README.md)。
