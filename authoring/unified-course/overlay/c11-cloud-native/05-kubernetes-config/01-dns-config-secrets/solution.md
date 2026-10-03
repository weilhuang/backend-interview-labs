# 标准答案

完整可运行的service.yaml、config.yaml、rbac.yaml与AppConfig.java在answers/。

Service的selector是app=orders，type=ClusterIP，port=8080，targetPort=http；Deployment声明名为http的containerPort=8080。labels必须匹配，名称相似不会自动建立关系。

REDIS_HOST来自ConfigMap键redis-host，值为redis；AppConfig用env.getOrDefault("REDIS_HOST", "redis")。容器边界下localhost指API自身，故该错误配置被显式拒绝。

密码仅从REDIS_PASSWORD_FILE读取。load验证密码长度但不把值放入异常。toString返回redacted。banner()每次读取挂载文件，greeting则是record中创建时固定的字符串。Java测试直接修改临时文件与原Map，验证这两种语义确实不同。

两种常见配置更新策略都可合理：本题演示非敏感公告文件按请求重读；另一种是带配置版本的Deployment滚动发布，把配置与程序版本绑定。前者延迟最终一致，后者更易审计但有发布开销；秘密轮换更需要服务端/客户端协调，不能简单照搬公告重载。

RBAC允许观察员读取Pod/Service/events/Deployment/ReplicaSet/EndpointSlice，不允许Secret读取、工作负载创建或跨namespace读取。RoleBinding只引用同namespace的observer。没有SA token自动挂载；auth can-i使用管理员受控模拟，不生成新的长期token。

真实验收必须有允许和拒绝双向证据；只看到禁止动作返回no，可能是账号根本没配置好。日志检查只能证明本次所采集应用日志未包含该合成值，不能外推整个集群从不泄漏Secret。
