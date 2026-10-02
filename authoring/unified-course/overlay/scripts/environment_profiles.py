"""环境映射只描述依赖；题目路径与 Gradle 项目名唯一来自 course-map.json。"""
PROFILES = {
    'java': (),
    'mysql': ('mysql',),
    'redis': ('redis',),
    'redis-mysql': ('mysql', 'redis'),
    'kafka': ('kafka',),
    'kafka-mysql': ('mysql', 'kafka'),
    'rocketmq': ('rocketmq',),
    'rocketmq-mysql': ('mysql', 'rocketmq'),
    'kafka-rocketmq': ('kafka', 'rocketmq'),
    'distributed-outbox': ('mysql', 'redis', 'kafka'),
    'capstone': ('mysql', 'redis', 'kafka', 'delivery', 'orders'),
}


def profile_for(task):
    source = task['source_course']
    path = task['source_task']
    leaf = path.rsplit('/', 1)[-1]
    if source in ('cloud-native', 'observability', 'go', 'identity'):
        return 'java'  # Native bridge needs no pre-started middleware; see explicit capability map.
    if source == 'mysql-engineering':
        return 'mysql'
    if source == 'redis-engineering':
        return 'redis-mysql' if leaf in ('04-consistency', '06-leases', '07-resilience') else 'redis'
    if source == 'java-frameworks' and leaf == '03-transactions':
        return 'mysql'
    if source == 'distributed-systems':
        if leaf == '07-outbox-cache':
            return 'distributed-outbox'
        return 'mysql' if leaf in ('05-idempotency', '06-transactions', '08-capacity') else 'java'
    if source == 'messaging':
        lesson = path.split('/')[1]
        if path.startswith('kafka/'):
            return 'kafka-mysql' if lesson in ('03-inbox', '06-recovery') else 'kafka'
        if path.startswith('rocketmq/'):
            if lesson == '06-comparison':
                return 'kafka-rocketmq'
            return 'rocketmq-mysql' if lesson == '04-transactions' else 'rocketmq'
        raise ValueError('未知 MQ 题目路径：' + path)
    if source == 'backend-capstone':
        return 'capstone'
    if source in ('java-foundations', 'java-concurrency', 'java-jvm'):
        return 'java'
    if source == 'java-frameworks':
        return 'java'
    raise ValueError('未知来源课程，须补齐环境映射：' + source)


def topology_note(task):
    path = task['source_task']
    if task['source_course'] in ('cloud-native', 'observability', 'go', 'identity'):
        return '原生桥接仅验证本地合同；Go需显式工具链，IAM含真实本地HTTP；Docker/Kubernetes/外部观测后端未接入，不等于完整基础设施验收'
    if task['source_course'] == 'redis-engineering' and path.endswith('/05-replication'):
        return '完整测试会创建主从 Redis；手动 redis profile 仅单节点，不能代替复制实验'
    if task['source_course'] == 'distributed-systems' and path.endswith('/06-transactions'):
        return '完整测试会创建两个独立 MySQL；手动 mysql profile 仅单节点'
    if task['source_course'] == 'messaging' and path.startswith('kafka/06-recovery/'):
        return '完整测试含三 broker Kafka 副本场景及 MySQL；手动 profile 仅单 broker'
    if task['source_course'] == 'messaging' and path.startswith('rocketmq/06-comparison/'):
        return '完整测试依次创建 Kafka 与 RocketMQ，避免为对照题常驻两套队列'
    return '真实测试使用独立临时容器与随机端口；不复用手动演示数据卷' if profile_for(task) != 'java' else '无需预先启动中间件'
