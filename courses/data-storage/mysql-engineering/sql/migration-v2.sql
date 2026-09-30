-- 只迁移本课请求编号列：区分大小写与尾空格，避免业务ID被默认排序规则合并。
ALTER TABLE c06_orders MODIFY request_id VARCHAR(80) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL;
ALTER TABLE c06_reservation MODIFY request_id VARCHAR(80) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL;
