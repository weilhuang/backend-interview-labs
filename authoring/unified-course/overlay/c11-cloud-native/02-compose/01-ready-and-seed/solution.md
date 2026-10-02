# C11-02 中文逐步答案

1. 唯一ready真值是依赖健康、已seed且未drain。参考逻辑式为 `dependencyHealthy && seeded && !draining`；参考显式分支先拒绝draining，再拒绝不健康，最后返回seeded
2. /live仅报告进程能响应；不要把Redis错误灌入liveness。/ready执行真实PING和schema读取，所以依赖不可用会通过统一异常映射返回503及layer
3. Compose先等Redis service_healthy，API启动后/downstream-check可用于初始化前检查。API容器healthcheck仍用/ready，但入口不能在seed前无限等它healthy
4. seed一次Lua完成“已存在则不写；不存在则同时写schema和stock”。所以买掉2份后再seed不会变回10
5. 订单脚本先查幂等记录：同输入返回旧结果，不同数量拒绝；无记录才检查和扣库存。库存与结果同一原子脚本写入
6. 验证重启必须对照先前库存值；只看新进程200不能证明数据没丢
7. stop保留数据卷和namespace。真实测试使用新分配的verify namespace，不以FLUSHALL或删除volume获得干净状态

完整答案：共享src/labs/CloudPolicy.java；另一种正确写法：answers/CloudPolicy-explicit.java.txt。测试绝不能因starter失败就把期望ready从false改成true。

生产迁移提醒：本课seed只建立新实验数据，不能把已有schema版本升级问题含混成“已存在就不管”；密码只是合成教学配置，不应复用真实账号。
