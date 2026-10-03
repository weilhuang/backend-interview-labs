# C11-01 中文逐步答案

1. 首个FROM只负责构建：输入src，输出classes。`--release 21`约束生成的Java字节码与可用API，不会把旧编译器变成新编译器
2. 第二个FROM从统一JRE镜像开始。不要继承build阶段，否则编译器和源码仍在最终层中
3. 从build明确复制classes；另复制web。这是本应用运行所需的全部自有文件
4. 使用数值UID/GID与COPY归属配合。应用写数据由Redis完成，本地不需要写源码目录
5. `ENTRYPOINT ["java", ...]`让Java成为主进程。变体脚本必须最后exec，不能只“用了数组就安全”，数组里启动`sh -c`仍要检查shell行为
6. `CloudNativeApp.stop()`先draining，再等待已经进入处理器的请求。Docker外层6秒大于应用3秒+线程池1秒，留出收尾空间；预算是教学契约，生产要按工作负载测量
7. 验证镜像内没有javac/Maven/应用.env，不能用“Dockerfile有两个FROM”替代结果检查
8. 将完整参考文件与starter做diff，指出每个改动对应哪一条失败断言。最终仍须运行真实Docker测试，不接受仅格式检查

参考A：共享`answers/Dockerfile.exec`。参考B：共享`answers/Dockerfile.exec-script`和`container/entrypoint.sh`。

参考输出不固定镜像字节大小，因为不同架构与基础镜像层可能不同；固定的是非root、允许文件、业务和停止行为。不要为了匹配截图伪造大小或退出码。
