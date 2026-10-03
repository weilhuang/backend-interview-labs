# 官方来源与固定版本（核对日期2026-10-02 UTC）

资料只使用项目官方文档/官方代码库。动态网页会更新，下面固定release与本仓库版本证据负责复现边界；没有伪造运行验证。

## 工具与镜像

- kind v0.33.0 release：<https://github.com/kubernetes-sigs/kind/releases/tag/v0.33.0>。该release明确列出Kubernetes v1.36.4的node镜像digest，以及amd64/arm64支持。选择此同release构建组合；镜像尚未拉取执行
- kind节点镜像兼容边界：<https://kind.sigs.k8s.io/docs/design/node-image/>。不依赖node内部实现
- kind配置：<https://kind.sigs.k8s.io/docs/user/configuration/>。API只绑定127.0.0.1，单节点，无宿主目录挂载、无公网端口
- kind镜像加载：<https://kind.sigs.k8s.io/docs/user/quick-start/#loading-an-image-into-your-cluster>。应用镜像本地构建后load，Pod imagePullPolicy=Never
- Kubernetes版本偏移：<https://kubernetes.io/releases/version-skew-policy/>。本批更严格地选kubectl/server相同v1.36.4
- 原仓库台账固定证据：<https://github.com/weilhuang/backend-interview-labs/blob/8d34917b0e0ecc33968e4e1d032a27045e91fa8e/infra/versions.env>。复用JAVA_BUILD_IMAGE与REDIS_IMAGE，不新建一组替代镜像
- JRE复用Docker前三课JAVA_RUNTIME_IMAGE提案：Temurin21固定tag+digest。候选不改原台账，新增Kind项只在integration/versions.env.additions提案

Redis上游台账目前固定tag而未固定digest，driver记录实际拉取后的本地image ID用于当前run。此证据不等于跨时点tag绝不变化；最终发布需统一台账策略审计，不能在本候选私自换Redis版本。

## Kubernetes机制

- 探针：<https://kubernetes.io/docs/concepts/workloads/pods/probes/> 与 <https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/>
- Deployment更新/回滚：<https://kubernetes.io/docs/concepts/workloads/controllers/deployment/>
- Service DNS：<https://kubernetes.io/docs/concepts/services-networking/dns-pod-service/>
- ConfigMap：<https://kubernetes.io/docs/concepts/configuration/configmap/>
- Secret：<https://kubernetes.io/docs/concepts/configuration/secret/>
- RBAC：<https://kubernetes.io/docs/reference/access-authn-authz/rbac/>
- 资源管理：<https://kubernetes.io/docs/concepts/configuration/manage-resources-containers/>

固定源码阅读入口：<https://github.com/kubernetes/kubernetes/tree/v1.36.4/pkg/controller/deployment>（状态收敛与发布），<https://github.com/kubernetes/kubernetes/tree/v1.36.4/pkg/kubelet/prober>（探针调度）。仅作为标签固定的后续阅读入口，未宣称本次逐行审计源码。

## JetBrains Academy

- 官方Java课程模板：<https://github.com/jetbrains-academy/java-course-template>
- 官方task-info.yaml示例：<https://github.com/jetbrains-academy/java-course-template/blob/main/courseSection/courseLesson/programmingTask/task-info.yaml>，本次读取blob 4d4fc5ec294b5c25579a6981a4860d9ac0ffa9d9
- 官方YAML占位说明与可编辑边界：<https://youtrack.jetbrains.com/projects/EDU/issues/EDU-8912/Placeholders-in-YAML>

由此采用type: edu、files.name/visible/placeholders、UTF-16 offset/length和placeholder_text。作者文件放完整答案、学习者投影还原starter，公开测试文件visible=true。存在元数据只证明结构候选，必须再跑原生预览/Check和错误解标记传播，当前NOT_RUN。
