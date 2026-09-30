# 固定版本的官方来源与证据

源码基线mysql/mysql-server的mysql-8.4.7标签。2026-09-30通过GitHub连接器读取实际文件并验证以下符号。这里只链接与讲解，未复制MySQL源代码；许可证见原仓库GPL-2.0。文件SHA为Git blob SHA，不当作整个仓库commit。

| 单元 | 文件与符号 | 已读文件SHA |
|---|---|---|
| 01 | [row0ins.cc](https://github.com/mysql/mysql-server/blob/mysql-8.4.7/storage/innobase/row/row0ins.cc)：row_ins_check_foreign_constraint | 61d251d0103926a85712501189292dbff078501a |
| 02 | [sql_optimizer.cc](https://github.com/mysql/mysql-server/blob/mysql-8.4.7/sql/sql_optimizer.cc)：JOIN::optimize、test_if_skip_sort_order | 6fc7d33dfeabd9b1dbad0b07e875234ac0f674a7 |
| 03 | [composite_iterators.cc](https://github.com/mysql/mysql-server/blob/mysql-8.4.7/sql/iterators/composite_iterators.cc)：LimitOffsetIterator::Read | bce8ba584b94ceb7f510e523203b35f3cdac5711 |
| 04 | [read0read.cc](https://github.com/mysql/mysql-server/blob/mysql-8.4.7/storage/innobase/read/read0read.cc)：ReadView::prepare、MVCC::view_open | 0091cda99bd257cb239517044d82a4fa20752fbb |
| 04/07 | [row0sel.cc](https://github.com/mysql/mysql-server/blob/mysql-8.4.7/storage/innobase/row/row0sel.cc)：row_search_mvcc、row_sel_build_prev_vers_for_mysql | 03f4c8000f4e6632a9549046a6181470207aa7c1 |
| 05 | [lock0lock.cc](https://github.com/mysql/mysql-server/blob/mysql-8.4.7/storage/innobase/lock/lock0lock.cc)：lock_rec_lock、lock_rec_insert_check_and_lock | a42f51a4a8d899456fdbd7be83345b3f820c94f3 |
| 06 | [log0write.cc](https://github.com/mysql/mysql-server/blob/mysql-8.4.7/storage/innobase/log/log0write.cc)：log_write_up_to | a72f9db24ca69981c6a6a8c500a0a0c49890a760 |

官方机制文档：
- [MySQL8.4隔离级别](https://dev.mysql.com/doc/refman/8.4/en/innodb-transaction-isolation-levels.html)
- [一致性非锁定读](https://dev.mysql.com/doc/refman/8.4/en/innodb-consistent-read.html)
- [锁类型](https://dev.mysql.com/doc/refman/8.4/en/innodb-locking.html)
- [EXPLAIN](https://dev.mysql.com/doc/refman/8.4/en/explain.html)
- [InnoDB恢复](https://dev.mysql.com/doc/refman/8.4/en/innodb-recovery.html)
- [Testcontainers MySQL模块](https://java.testcontainers.org/modules/databases/mysql/)
- [Academy官方课程格式文档](https://plugins.jetbrains.com/plugin/10081-jetbrains-academy/docs)
- Wrapper/Academy结构复用仓库已核验Java试点，原始官方模板许可保留在LICENSE-JetBrains-template

运行镜像由共享清单选择，课程不固定第二个tag。源码阅读与二进制调试器单步是不同证据：后者尚未执行。

新增真实连接池源码：
- [HikariCP-6.2.1 ProxyConnection.close](https://github.com/brettwooldridge/HikariCP/blob/HikariCP-6.2.1/src/main/java/com/zaxxer/hikari/pool/ProxyConnection.java)，已核验Git blob SHA：02526d0cb98df74b961db2032a7a26bb1f055edb。关键分支为未自动提交且dirty时rollback、重置dirtyBits对应会话状态、finally回收到池。池代理close与物理TCP关闭不同，池整体close才结束其生命周期
- [MySQL8.4 GTID复制](https://dev.mysql.com/doc/refman/8.4/en/replication-gtids.html)与[WAIT_FOR_EXECUTED_GTID_SET](https://dev.mysql.com/doc/refman/8.4/en/gtid-functions.html)用于明确等待指定已提交位置，本课使用暂停副本SQL线程的确定性实验，不把复制延迟猜成固定sleep

请求ID比较依据：[MySQL8.4 Unicode排序规则](https://dev.mysql.com/doc/refman/8.4/en/charset-unicode-sets.html)明确utf8mb4_0900_bin为NO PAD，尾空格参与比较。
