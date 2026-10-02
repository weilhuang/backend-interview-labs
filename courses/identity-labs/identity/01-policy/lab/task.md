# C15-01 登录成功以后，谁有权读订单？

你接手两家合成公司的订单系统。reader可以读，editor/admin可以读和审批，但所有角色都只能访问自己租户的订单。前端已提供，不要求编写页面。

## 先读懂，再运行
先按根README准备已批准的JDK21/Gradle8.10.2并生成、检查固定依赖锁；当前所有Java层均NOT_RUN。
先读 `src/labs/identity/Usage.java` 三次调用，手算期望：同租户读取应ALLOW，reader审批应ROLE_DENIED，跨租户读取应TENANT_MISMATCH。完成策略，或在隔离副本中选择参考解后，才运行 `gradle --no-daemon :identity-01-policy-lab:usage` 对照这些期望。首次学习先读“资料/先修与身份概念卡.md”前两组与5道诊断，LDAP/OIDC后续再读。

## 阶段一：看懂契约（两个概念：认证与授权）
`Subject` 是调用者，`Resource` 是仓库中的订单，`action` 是本次动作。返回Decision不能只说true/false，还要给固定理由。已认证只说明凭证可信，不能推出某订单可访问。

契约顺序：缺主体/未认证/空身份 → UNAUTHENTICATED；缺资源ID或租户 → MISSING_ATTRIBUTE；跨租户 → TENANT_MISMATCH；未知动作 → UNKNOWN_ACTION；角色没有该权限 → ROLE_DENIED；否则ALLOW。输入不完整不得抛空指针，也不得放行。

## 阶段二：补完一个行为（两个概念：租户与角色表）
只编辑 `Policy.authorize` 的可填区，实现上述顺序。保留接口、测试、默认拒绝和两种角色语义。不要通过隐藏前端按钮、信任X-Role请求头或返回固定true完成。

Java小注：record把输入/输出组成明确值对象；Set表示无重复角色集合；Map把角色映射成允许动作；anyMatch表示“至少一个角色明确允许”。这些语法在代码注释与答案里按用途解释。

运行 `gradle --no-daemon :identity-01-policy-lab:test`。公开测试有11个固定顶层方法，其中矩阵方法内部从角色、动作、租户、认证四维验证144组。另有null/空白输入、完整reason、拒绝优先级和角色快照测试。双答案必须分别用同一套测试验证。starter以UnsupportedOperationException表示未完成；它设计为可编译，但实际编译尚待验收。验收应确认编译成功后业务断言失败，不能把编译失败算作正确检测。

## 阶段三：用反例证明（两个概念：对象归属与默认拒绝）
手算tenant-a管理员读取tenant-b订单，解释为什么admin仍被拒绝。再把动作换成user:delete，说明未知动作不能被“最高权限”短路。删除租户检查、把token视为管理员、admin任意动作等错误解必须能被业务断言杀死。

完整Spring调用链/现成前端源码位于 `materials/identity/identity-lab`。Gradle配置要求它在验证JWT之后从唯一学员jar加载Policy，实际来源仍需Java测试确认；纯策略通过不等于服务器、LDAP、Keycloak、浏览器SSO都已通过。各层证据分别报告。

## H1–H4 提示
- H1：先列拒绝情况，最后才考虑允许；不要从“哪个角色最大”开始
- H2：主体租户来自可信身份适配，资源租户来自服务端仓库，比较的是两种来源
- H3：先确认动作在白名单，再查每个角色的权限集合；未知角色映射空集合
- H4：Map版本用getOrDefault(role, Set.of())后anyMatch；显式版本用read/write布尔量加reader/editor/admin分支，两种都要保留同一拒绝顺序

下一步：资料中的迁移题让你增加order:cancel，并保持所有旧反例。答案、源码锚点、ASCII与渲染图都可见。请先独立作答，再比对“答案.md”。

新增反例：wrong-reasons保留boolean但乱改reason；empty-identifiers漏掉空标识；wrong-precedence先检查动作再检查租户。它们有可见源码，仍需在获准Java窗口证明被业务断言检测。
