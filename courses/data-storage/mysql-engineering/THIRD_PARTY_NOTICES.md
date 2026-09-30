# 第三方组件与使用边界

- Gradle Wrapper与课程格式沿用同仓库java-recovery-collections内核验的官方JetBrains Java课程模板，保留LICENSE-JetBrains-template
- Gradle8.10.2（Apache-2.0），JUnit5.11.4（EPL-2.0），Testcontainers1.20.6（MIT），HikariCP6.2.1（Apache-2.0），均通过构建依赖解析，课程包不内嵌其二进制（Wrapper例外）
- MySQL Connector/J9.2.0与MySQL服务端的许可/例外以官方发行版文件为准；本课程只提供原创教学代码和公开源码链接，没有复制服务端源码
- sql/schema.sql和seed.sql仅含合成数据，无真实用户、订单或密码；测试容器密码明确为隔离实验fixture，不用于任何实际账号
- 外部网页随时间更新，真实源码教学固定mysql-8.4.7和HikariCP-6.2.1标签，来源和文件SHA见SOURCES.md
