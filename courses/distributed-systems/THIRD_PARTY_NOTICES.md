# 第三方来源与许可

- Gradle Wrapper及Academy结构参考仓库已有JetBrains官方Java课程模板，随附原始LICENSE-JetBrains-template；实际导入状态单独验收
- gRPC Java、Protocol Buffers、Dubbo、Resilience4j、Kafka、ZooKeeper、Curator、Jedis、Testcontainers等依赖按各自原始许可证使用；没有移除上游版权声明
- `02-grpc/src/labs/distributed/grpc/protocol/`为由自有proto通过固定protoc4.29.0和grpc代码生成器1.71.0生成的公开完整代码，保留生成注释；不要把它当作需要逐行手写的练习
- 教学中引用的实际上游源码链接固定到提交哈希，标签解析、文件字节哈希可在authoring/source-verification.json核对；不引用移动main/master代替版本
- MySQL镜像、驱动以及Redis镜像的许可与部署适用性需要在真实商业环境另行评审；本仓库隔离教学使用不构成法律意见
