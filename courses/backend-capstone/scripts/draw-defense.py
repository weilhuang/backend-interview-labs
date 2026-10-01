#!/usr/bin/env python3
"""公开题库随机抽题；不遮挡标准解，也不伪称评分证明了掌握程度。"""
import random
faults=['HTTP在数据库提交后丢失响应：说明为什么不能换新请求号，并补一条回归','outbox已标记但inbox仍为空：用证据区分Kafka和RPC边界','Redis恢复后查询短暂旧值：复现读后写回竞态，解释TTL与强一致查询','旧取消事件晚到：说明版本比较如何保持读模型单调']
changes=['新商品pen初始库存10：不改Java常量，扩展独占测试数据并验证跨商品隔离','把每次最多100件改为20件：新增边界测试，验证其他不变量不变','把审计输出按ERROR在前、subject字典序排列：保持返回集合不可变','给GET查询返回缓存命中来源：不能让业务扣减读取缓存']
designs=['若每秒一万请求竞争一个SKU，先测什么再优化？','独立拆分配送数据库后，审计快照怎样重新设计？','怎样定义并回收幂等记录，同时保护迟到重试？','为什么单节点Kafka的acks=all不是集群容灾证明？']
for name,choices in [('故障',faults),('需求',changes),('设计',designs)]:print(name+'：'+random.SystemRandom().choice(choices))
print('先独立作答与编码，再看docs/答辩与盲测标准解.md。记录2/5/15分钟陈述以及没有实测的范围。')
