# C14真实中文页面与恢复证据

来源：[成功CI 36746760606](https://github.com/weilhuang/backend-interview-labs/actions/runs/36746760606)，[job 109994788807](https://github.com/weilhuang/backend-interview-labs/actions/runs/36746760606/job/109994788807)。PR源提交为 `1fb27d8885bf1eb62b112d2e15f5478becf697fa`；runner实际checkout合并提交为 `6f93d2e67d532f0ecd9caadefe0a7a8903e371e5`。

[原始artifact 11112663907](https://github.com/weilhuang/backend-interview-labs/actions/runs/36746760606/artifacts/11112663907)于2026-09-30 16:56:20 UTC生成，保留期至2026-10-07。下载的ZIP SHA-256已核对为 `c4311fa90ab208a61cab48f4ac72bd9566d2f317f4f767a61c4c45f086db5626`。本目录保留两个代表性PNG和两个原始JSON，逐字节复制，未修图、未缩放、未改写JSON。

## 截图与实查结果

- [390像素手机截图](ci-36746760606-390px.png)，原始390×2947像素
- [1440像素桌面截图](ci-36746760606-1440px.png)，原始1440×1874像素

原归档五个视口（320/390/800/801/1440）的完整PNG均已实际查看：中文字符正常，表单、健康指标、诊断和操作历史可读；800与801像素分别显示单列和双列断点。窄屏长身份表格按设计局部滚动，截图在滚动回左侧后拍摄，因此不会同时展示右侧全部字段。CI在320/390像素已实际执行“滚到最右并检查最后列可见”断言，成功日志与相同源提交的browser-smoke.mjs共同证明这一步，不能只凭静态截图推断。

下面宽度取自原始[布局JSON](ci-36746760606-browser-layout.json)，单位为CSS像素：

| 视口 | document/body宽度 | 订单容器/内容宽度 | 配送容器/内容宽度 |
|---|---|---|---|
| 320 | 320/320 | 258/837 | 258/1226 |
| 390 | 390/390 | 328/837 | 328/1226 |
| 800 | 800/800 | 738/837 | 738/1226 |
| 801 | 801/801 | 351/837 | 351/1226 |
| 1440 | 1440/1440 | 838/838 | 838/1226 |

所有外层容器均在视口边界内，两个表格的overflowX均为auto，整页未以隐藏溢出掩盖问题。长请求号是后端合同允许的64字符真实身份；提交、同号重试、409冲突、取消、Kafka/gRPC重放及CANCELLED / 2投影均由真实Compose服务提供。浏览器保持Chromium沙箱启用。

## 测试与恢复

原始JUnit共11套件、40方法（35快测＋5真实容器方法），failure/error/skipped均为0：

- labs.capstone.ContractTest：6方法
- labs.capstone.ReliabilityIntegrationTest：2方法
- labs.capstone.ReliabilityTest：6方法
- labs.capstone.DeliveryIntegrationTest：1方法
- labs.capstone.BrokerConfigTest：3方法
- labs.capstone.DeliveryTest：7方法
- labs.capstone.WireTest：1方法
- labs.capstone.RecoveryIntegrationTest：1方法
- labs.capstone.RecoveryTest：5方法
- labs.capstone.DefenseIntegrationTest：1方法
- labs.capstone.AuditTest：7方法

五阶段正反解报告均为真：参考实现、另一正确写法通过；可编译学习起点及已知错解被断言拒绝。脚本安全11场景通过。完整应用installDist、五个Usage、真实HTTP幂等/冲突/取消与投影也均在该CI通过。

[原始进程恢复JSON](ci-36746760606-process-recovery.json)的四项结果均为true：订单Java进程SIGKILL后恢复、配送Java进程SIGKILL时重放拒绝伪成功、配送进程重建后同身份重放、取消后审计。杀停发生于HTTP确认之后或RPC调用之前；精确提交后丢应答窗口另由显式故障注入测试。不能把它解释成MySQL提交确认网络包丢失实验。

运行工具：Temurin21.0.12.1+1、Gradle8.10.2、Playwright1.62.1、Google Chrome153.0.8010.52、Noto Sans CJK SC（Ubuntu fonts-noto-cjk 1:20230817+repack1-3）。

## 校验与边界

- `ci-36746760606-390px.png` SHA-256：`6a08d1a625f0ae997c4158731c24d21a9bc8f8c1623961149e3c2f933e790e6c`
- `ci-36746760606-1440px.png` SHA-256：`2d580e96019876e857db21b5f8beca7992f14e5330c65ca8f7440c618a19e9e3`

归档中authoring/verification-report.json是运行开始前checkout的静态报告，仍记载上一轮失败和“待运行”；本轮结论以原始JUnit、恢复/布局JSON、步骤结论及job日志为准，当前仓库汇总已据这些原始证据更新。

这些材料证明该源提交的C14命令行、真实服务与Chrome中文前端门禁通过，不代表整个V1发布完成、不代表macOS Compose实测，不证明所有长SKU/审计文本或触屏设备组合已覆盖，也不代表本课程IDEA/Academy预览、Check/Run、重置、官方导出及干净导入验收完成。GUI验证另行记录。
