# 上游出处与使用说明

- Academy结构与Gradle失败输出协议参考JetBrains官方Java课程模板固定提交[c23b40acc8e1a0628e036598935ee6139cca0077](https://github.com/jetbrains-academy/java-course-template/tree/c23b40acc8e1a0628e036598935ee6139cca0077)。Wrapper源文件来自该模板，MIT许可证保留在LICENSE-JetBrains-template。本课不是JetBrains官方课程
- Wrapper分发版本为Gradle8.10.2，校验和已写入gradle/wrapper/gradle-wrapper.properties；原始第三方脚本和许可证保留上游语言
- Java客户端为Jedis5.2.0、MySQL Connector/J9.2.0；JUnit5.11.4、Testcontainers1.20.6。构建从Maven Central解析，不将依赖JAR提交进课程
- Redis服务端阅读固定tag7.4.7，外链源码，不在本课程复制Redis实现。Redis7.4采用RSALv2/SSPLv1双许可，部署与分发自行遵守上游许可；教学阅读不等于可任意商用Redis源码
- 本项目自行编写的Java、中文任务、测试和标准解为教学交付。故障编排只操作Testcontainers自行创建的临时资源
- 源码网页和CLI静态校验不等同于已通过Academy预览、检查、重置、导出与干净导入；这些仍需IDE实测
