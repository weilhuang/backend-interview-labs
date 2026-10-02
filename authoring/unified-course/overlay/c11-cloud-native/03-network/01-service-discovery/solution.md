# C11-03 中文逐步答案

1. 连接由API容器中的RedisClient发起，因此localhost是API自身。返回redis服务名才会查找同网络中的Redis容器
2. 从环境读REDIS_HOST和REDIS_PORT；端口使用容器6379，不使用宿主API18085，也不盲抄其他Redis课程的宿主映射
3. 保留配置注入能力。测试会注入不同host/port，固定返回redis:6379仍是错误解
4. 默认配置思路与显式配置思路都可以；区别是缺配置时采用约定还是失败。报告时说清选择，不把一种政策宣称放之四海皆准
5. 传输层把UnknownHost归DNS，拒绝连接归CONNECT，连接/读取超时归TIMEOUT，Redis认证错误归AUTH，不回显密码。错误不能一律包装成200“服务已恢复”
6. 恢复不仅要PING，还要/ready、/stock和订单业务契约。连接到了空的错误Redis实例也可能PING成功
7. 不需要为Redis增加宿主ports，更不需要host网络或特权容器。临时诊断必须由本课严格project范围约束

完整参考：共享src/labs/AddressPolicy.java；显式配置变体：answers/AddressPolicy-explicit.java.txt。容器错误变体为localhost/错误端口，策略错误变体为忽略显式配置。两种错误必须分别被相应断言抓住。

DNS查找本身受操作系统解析器影响；600ms是TCP连接/读取超时，不应对外宣称整个名字解析过程严格600ms。真实环境还要验证DNS超时策略，这会在后续Kubernetes排障课扩展。
