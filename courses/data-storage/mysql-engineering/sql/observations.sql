-- 只读诊断：需要相应只读权限；不可访问时记录权限阻塞，不给教学用户全库管理员权限。
SELECT @@version, @@transaction_isolation, @@innodb_flush_log_at_trx_commit, @@sync_binlog, @@log_bin;
SELECT * FROM performance_schema.data_lock_waits;
SELECT ENGINE_TRANSACTION_ID, OBJECT_NAME, INDEX_NAME, LOCK_TYPE, LOCK_MODE, LOCK_DATA FROM performance_schema.data_locks WHERE OBJECT_NAME LIKE 'c06_%';
SHOW ENGINE INNODB STATUS;
SHOW BINARY LOG STATUS;
