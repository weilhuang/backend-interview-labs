#!/usr/bin/env python3
"""只对独立 CI 项目做真实读写/收发；不得指向学习者已有数据。"""
import os
from pathlib import Path
import re
import subprocess
import sys
import lab


def guarded_config():
    config, path = lab.settings()
    if os.environ.get('CI') != 'true' or not re.fullmatch(r'backend-interview-labs-ci-\d+-\d+', config['LAB_PROJECT_NAME']):
        raise lab.LabError('真实冒烟脚本仅允许 CI=true 且项目名为 backend-interview-labs-ci-运行号-重试号')
    return config, path


def execute(config, path, service, command, data=None):
    result = subprocess.run(lab.compose(config, path) + ['exec', '-T', service] + command,
                            env=lab.docker_env(config), input=data, text=True, capture_output=True, timeout=90)
    if result.returncode:
        raise lab.LabError(service + ' 真实读写命令失败；检查已脱敏 CI 日志')
    return result.stdout.strip()


def main(action):
    config, path = guarded_config()
    marker = config['LAB_PROJECT_NAME']
    mysql = ['sh', '-ec', 'MYSQL_PWD="$MYSQL_PASSWORD" exec mysql --protocol=TCP -h 127.0.0.1 -u "$MYSQL_USER" "$MYSQL_DATABASE" --batch --skip-column-names']
    redis = ['sh', '-ec', 'REDISCLI_AUTH="$REDIS_PASSWORD" exec redis-cli --raw "$@"', 'redis-cli']
    if action in ('core-write', 'core-read'):
        if action == 'core-write':
            sql = "CREATE TABLE IF NOT EXISTS lab_environment_smoke (id INT PRIMARY KEY, marker VARCHAR(120) NOT NULL); "
            sql += "INSERT INTO lab_environment_smoke VALUES (1, '" + marker + "') ON DUPLICATE KEY UPDATE marker=VALUES(marker); "
            sql += 'SELECT marker FROM lab_environment_smoke WHERE id=1;'
            if execute(config, path, 'mysql', mysql, sql) != marker:
                raise lab.LabError('MySQL 写入后读取值不一致')
            if execute(config, path, 'redis', redis + ['SET', 'lab:ci:smoke', marker]) != 'OK':
                raise lab.LabError('Redis 写入未返回 OK')
        else:
            sql = 'SELECT marker FROM lab_environment_smoke WHERE id=1;'
            if execute(config, path, 'mysql', mysql, sql) != marker:
                raise lab.LabError('MySQL 重启后数据不一致')
        if execute(config, path, 'redis', redis + ['GET', 'lab:ci:smoke']) != marker:
            raise lab.LabError('Redis 数据不一致')
        print('真实 MySQL 与 Redis 读写通过' if action == 'core-write' else '停止/重启后的 MySQL 与 Redis 数据持久化通过')
    elif action == 'kafka':
        execute(config, path, 'kafka', ['/opt/kafka/bin/kafka-topics.sh', '--bootstrap-server', 'localhost:9092',
                    '--create', '--if-not-exists', '--topic', 'lab-ci-smoke', '--partitions', '1', '--replication-factor', '1'])
        execute(config, path, 'kafka', ['/opt/kafka/bin/kafka-console-producer.sh', '--bootstrap-server', 'localhost:9092',
                    '--topic', 'lab-ci-smoke', '--producer-property', 'acks=all'], marker + '\n')
        got = execute(config, path, 'kafka', ['/opt/kafka/bin/kafka-console-consumer.sh', '--bootstrap-server', 'localhost:9092',
                    '--topic', 'lab-ci-smoke', '--from-beginning', '--max-messages', '1', '--timeout-ms', '30000'])
        if got != marker:
            raise lab.LabError('Kafka 收到的消息与发送内容不一致')
        print('真实 Kafka 建主题、发送及消费校验通过')
    elif action in ('rocketmq-write', 'rocketmq-read'):
        # 固定名称只在当前一次性 CI 项目的独立 Broker 内使用。
        roundtrip = ('lab_ci_roundtrip', 'lab_ci_roundtrip_group')
        durable = ('lab_ci_durable', 'lab_ci_durable_group')
        if action == 'rocketmq-write':
            admin = ['bash', '/opt/lab-rocketmq/admin.sh']
            for topic, group in (roundtrip, durable):
                execute(config, path, 'rocketmq', admin + ['updateTopic', '-n', '127.0.0.1:9876',
                        '-b', '127.0.0.1:10911', '-t', topic, '-r', '1', '-w', '1', '-a', '+message.type=NORMAL'])
                execute(config, path, 'rocketmq', admin + ['updateSubGroup', '-n', '127.0.0.1:9876',
                        '-b', '127.0.0.1:10911', '-g', group])
        target = lab.ROOT / 'infra' / 'rocketmq' / 'smoke' / 'target'
        if not (target / 'classes' / 'lab' / 'environment' / 'RocketSmoke.class').is_file():
            raise lab.LabError('请先用 JDK21 编译 infra/rocketmq/smoke，见共享环境 CI')
        mode = action.removeprefix('rocketmq-')
        result = subprocess.run(['java', '-Xmx256m', '-XX:MaxDirectMemorySize=64m', '-cp',
                    str(target / 'classes') + os.pathsep + str(target / 'dependency' / '*'),
                    'lab.environment.RocketSmoke', mode, '127.0.0.1:' + config['ROCKETMQ_PORT'],
                    *roundtrip, *durable, marker], text=True, capture_output=True, timeout=150)
        if result.returncode or ('ROCKETMQ_SMOKE_OK=' + mode) not in result.stdout.splitlines():
            # 仅项目自生成标记，不含凭据；保留 SDK 真正错误以便诊断。
            print((result.stdout + result.stderr)[-12000:], file=sys.stderr)
            raise lab.LabError('RocketMQ 宿主 gRPC 收发/持久化验收失败')
        print('真实宿主 RocketMQ gRPC 收发通过，并已留存重启检查消息' if mode == 'write'
              else 'down/up 后从宿主 gRPC 读回原消息并确认消费通过')
    elif action == 'logs':
        target = lab.ROOT / 'infra' / 'artifacts'
        target.mkdir(exist_ok=True)
        for service in ('mysql', 'redis', 'kafka', 'rocketmq'):
            result = subprocess.run(lab.compose(config,path)+['logs','--no-color','--tail','300',service],
                                    env=lab.docker_env(config), capture_output=True, text=True, timeout=60)
            text = result.stdout + result.stderr
            if service == 'rocketmq':
                detail = subprocess.run(lab.compose(config, path) + ['exec', '-T', 'rocketmq', 'bash',
                        '/opt/lab-rocketmq/logs.sh'], env=lab.docker_env(config), capture_output=True, text=True, timeout=30)
                text += '\n' + detail.stdout + detail.stderr
                containers = subprocess.run(lab.compose(config, path) + ['ps', '--all', '--quiet', 'rocketmq'],
                        env=lab.docker_env(config), capture_output=True, text=True, timeout=15)
                for container in containers.stdout.split():
                    if not re.fullmatch(r'[0-9a-f]{12,64}', container):
                        continue
                    state = subprocess.run(['docker', 'inspect', '--format', '{{json .State}}', container],
                            env=lab.docker_env(config), capture_output=True, text=True, timeout=15)
                    text += '\n容器状态（含退出码/OOM，不含环境变量）：\n' + state.stdout + state.stderr
            for key, value in config.items():
                if 'PASSWORD' in key:
                    text = text.replace(value, '[已脱敏]')
            with (target / (service + '.log')).open('a', encoding='utf-8') as f:
                f.write(text + '\n')
        print('组件日志已脱敏归档，不包含 .env 或 docker inspect 环境变量')
    else:
        raise lab.LabError('可用动作：core-write、core-read、kafka、rocketmq-write、rocketmq-read、logs')


if __name__ == '__main__':
    try:
        if len(sys.argv) != 2:
            raise lab.LabError('需要指定一个 CI 冒烟动作')
        main(sys.argv[1])
    except (lab.LabError, OSError, subprocess.TimeoutExpired) as exc:
        print('错误：' + str(exc), file=sys.stderr)
        sys.exit(2)
