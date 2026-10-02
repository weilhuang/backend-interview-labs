# C15 身份、租户与订单授权

这是独立源码草稿，状态 IMPLEMENTED_UNTESTED。Java编译、Gradle模型、实际HTTP、类来源和原生Academy验收均NOT_RUN；不把Python/mock检查当作这些层的通过证据。

## 学习内容
- 认证与授权的区别、默认拒绝、租户角色和资源归属
- 单一学员Policy实现，两种可见参考答案、六种可见错误解
- Spring资源服务、成熟JOSE验签、固定JWKS信任源与中文前端
- 公开测试覆盖输入缺失、空白、reason、拒绝顺序和144组权限矩阵
- JWT、真实HTTP与类来源测试已有源码，等待独立运行验收

阅读顺序：
1. [任务](identity/01-policy/lab/task.md)
2. [学员Policy源](identity/01-policy/lab/src/labs/identity/Policy.java)
3. [公开Policy测试](identity/01-policy/lab/test/labs/identity/PolicyTest.java)
4. [逐步答案](identity/01-policy/lab/答案.md)
5. [完整调用链](identity/01-policy/lab/资料/调用链与排错.md)

## 当前可用入口

本包使用已安装的Gradle命令。先准备已经批准的JDK21与Gradle8.10.2，并确认JAVA_HOME、PATH。下面的gradle均指该已安装版本。

依赖锁目前尚未生成，STRICT锁模式会阻止缺锁构建。仅在获准环境首次执行：
```sh
gradle --no-daemon --write-locks resolveAndLock
```
检查并固定两个模块的gradle.lockfile后，再用同一锁集验证所有参考/错误变体；不能每个场景各自更新依赖。

日常编写策略：
```sh
gradle --no-daemon :identity-01-policy-lab:test
```
这一入口会在学员测试后执行真实HTTP和Policy类来源门禁；后置任务失败也必须让整体命令失败。starter尚未实现，预期业务失败，不能以缺锁/编译/环境失败冒充它被正确检测。

完整源码测试：
```sh
gradle --no-daemon identityCheck
```
它增加服务侧JWT、MockMvc、LDAP转义辅助测试；真实LDAP/Keycloak容器与浏览器SSO仍未包含。

## 严格执行证据门禁

先固定依赖锁，再在源树外一个尚不存在的目录运行：
```sh
python scripts/verify_finalizedby_gate.py --gradle "$(command -v gradle)" --java-home "$JAVA_HOME" --output "../identity-gate-run-001"
```
脚本在隔离副本分别选table/explicit答案，再执行一次真实HTTP负探针。每个场景绑定runID、完整源文件hash、配置/工具hash和锁hash，禁缓存并强制重跑。正例必须11个Policy方法与4个HTTP/来源方法全绿；负例只能是专属读订单断言expected200/observed401这一项失败，其余全部通过，Gradle退出码必须1。

固定方法集在gate-contract.json；其中矩阵方法内部144组，不算144个JUnit顶层方法。首个获准Java运行还须确认XML格式；格式不符应阻塞并审查合同版本，不能降级为子串匹配。

普通Python回归：
```sh
PYTHONDONTWRITEBYTECODE=1 python -m unittest discover -s tests -v
```
它mock进程边界验证判定器，不启动Java/Gradle/HTTP。完整mock被接受只代表解析器接受了合格形状数据，不是实际服务通过。可信工具链与测试源码仍是证据的前提，解析器不能抵御任意恶意执行器伪造。

本目录尚不是可直接完整导入的Academy课程包；现有task源、资料与元数据用于后续整合和原生验收。
