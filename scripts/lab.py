#!/usr/bin/env python3
"""共享实验入口：只使用 Python 标准库，不安装软件、不清理其他项目。"""
import argparse
import json
import os
from pathlib import Path
import platform
import re
import shutil
import socket
import time
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
INFRA = ROOT / 'infra'
GROUPS = {'core': ['mysql', 'redis'], 'mysql': ['mysql'], 'redis': ['redis'], 'kafka': ['kafka'], 'rocketmq': ['rocketmq']}
PORTS = {'mysql': ('MYSQL_PORT', 3306), 'redis': ('REDIS_PORT', 6379), 'kafka': ('KAFKA_PORT', 19092), 'rocketmq': ('ROCKETMQ_PORT', 8081)}
PORT_KEYS = tuple(key for key, _ in PORTS.values())
COMPOSE_IMAGE_KEYS = {'MYSQL_IMAGE', 'REDIS_IMAGE', 'KAFKA_IMAGE', 'JAVA_BUILD_IMAGE', 'ROCKETMQ_IMAGE'}
IMAGE_KEYS = COMPOSE_IMAGE_KEYS | {'TESTCONTAINERS_RYUK_IMAGE', 'TESTCONTAINERS_TINY_IMAGE'}
CONFIG_KEYS = {'LAB_PROJECT_NAME', 'MYSQL_PORT', 'REDIS_PORT', 'KAFKA_PORT', 'ROCKETMQ_PORT', 'MYSQL_DATABASE',
               'MYSQL_USER', 'MYSQL_PASSWORD', 'MYSQL_ROOT_PASSWORD', 'REDIS_PASSWORD', 'LAB_WAIT_SECONDS'}

class LabError(Exception):
    """可直接显示给学习者的错误，不包含密码。"""

def read_env(path):
    """只读严格的键值文件，绝不执行 shell 内容。"""
    values = {}
    for n, raw in enumerate(path.read_text(encoding='utf-8').splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith('#'):
            continue
        if '=' not in line:
            raise LabError(f'{path.name} 第 {n} 行应为 KEY=VALUE')
        key, value = line.split('=', 1)
        if not re.fullmatch(r'[A-Z][A-Z0-9_]*', key) or not value or re.search(r'[\s\x00-\x1f\x7f\x22\x27`$\\]', value):
            raise LabError(f'{path.name} 第 {n} 行格式无效：不允许引号、空格、变量或命令')
        if key in values:
            raise LabError(f'{path.name} 中有重复键 {key}')
        values[key] = value
    return values

def settings(init=False):
    path = INFRA / '.env'
    if init and not path.exists():
        # 使用排他创建，避免覆盖学习者已保存的配置。
        try:
            with path.open('x', encoding='utf-8') as f:
                f.write((INFRA / '.env.example').read_text(encoding='utf-8'))
            path.chmod(0o600)
            print('已创建 infra/.env：仅含实验示例密码，请勿提交或复用到真实系统。')
        except FileExistsError:
            pass
    config = read_env(path if path.exists() else INFRA / '.env.example')
    if set(config) != CONFIG_KEYS:
        raise LabError('infra/.env 配置键不完整或包含未知键，请对照 .env.example；镜像版本只能改 versions.env')
    if not re.fullmatch(r'backend-interview-labs(?:-[a-z0-9-]+)?', config['LAB_PROJECT_NAME']):
        raise LabError('LAB_PROJECT_NAME 必须是 backend-interview-labs，或加 -个人后缀（小写字母/数字/连字符）')
    for key in ('MYSQL_DATABASE', 'MYSQL_USER'):
        if not re.fullmatch(r'[a-zA-Z][a-zA-Z0-9_]{0,31}', config[key]):
            raise LabError(f'{key} 仅允许字母开头的字母、数字和下划线，最多 32 字符')
    if config['MYSQL_USER'].lower() == 'root':
        raise LabError('MYSQL_USER 应使用实验普通用户，不能设为 root')
    for key in ('MYSQL_PASSWORD', 'MYSQL_ROOT_PASSWORD', 'REDIS_PASSWORD'):
        if not re.fullmatch(r'[A-Za-z0-9_!@%+=.,:-]{12,128}', config[key]):
            raise LabError(f'{key} 需为 12–128 位实验密码；仅用字母数字及 _!@%+=.,:-')
    for key in PORT_KEYS:
        if not config[key].isdigit() or not 1024 <= int(config[key]) <= 65535:
            raise LabError(f'{key} 必须为 1024–65535 之间的端口')
    if len({int(config[k]) for k in PORT_KEYS}) != len(PORT_KEYS):
        raise LabError('所有组件的宿主端口不能重复（含 RocketMQ）')
    if not config['LAB_WAIT_SECONDS'].isdigit() or not 30 <= int(config['LAB_WAIT_SECONDS']) <= 900:
        raise LabError('LAB_WAIT_SECONDS 必须为 30–900 秒')
    return config, path if path.exists() else INFRA / '.env.example'

def versions():
    values = read_env(INFRA / 'versions.env')
    if set(values) != IMAGE_KEYS:
        raise LabError('版本台账必须完整包含已登记的 IMAGE 键，不能缺失或加入未知键')
    for key, value in values.items():
        if not re.fullmatch(r'[a-z0-9./-]+:\d+\.\d+\.\d+[a-zA-Z0-9_.-]*(?:@sha256:[a-f0-9]{64})?', value):
            raise LabError(f'{key} 必须锁定完整版本标签，可附多架构 sha256 摘要；禁止 latest/浮动版本')
    return values

def validate():
    """静态约束检查不等同于真实 Compose/容器验证。"""
    manifest = versions()
    settings()
    spec = json.loads((INFRA / 'compose.yaml').read_text(encoding='utf-8'))
    if set(spec['services']) != {'mysql', 'redis', 'kafka', 'rocketmq', 'java-build'}:
        raise LabError('Compose 服务集合与入口不一致')
    used = set()
    for name, service in spec['services'].items():
        key = service['image'].removeprefix('${').removesuffix('}')
        if service['image'] != '${' + key + '}' or key not in manifest:
            raise LabError(f'{name} 必须从唯一版本台账引用镜像')
        used.add(key)
        for p in service.get('ports', []):
            if not p.startswith('127.0.0.1:'):
                raise LabError(f'{name} 禁止开放到非回环地址')
        if service.get('privileged') or service.get('network_mode') == 'host' or 'platform' in service:
            raise LabError(f'{name} 不允许特权、宿主网络或强制架构仿真')
        if any('docker.sock' in str(v) for v in service.get('volumes', [])):
            raise LabError('基础实验不允许挂载 Docker socket')
        if name != 'java-build' and 'healthcheck' not in service:
            raise LabError(f'{name} 缺少健康检查')
        if 'mem_limit' not in service or 'logging' not in service:
            raise LabError(f'{name} 缺少内存或日志边界')
    if spec['services']['rocketmq']['profiles'] != ['rocketmq']:
        raise LabError('RocketMQ 只能显式按需启动，不能加入 core/tools')
    if used != COMPOSE_IMAGE_KEYS:
        raise LabError('Compose 与版本台账未完整对应')
    return spec

def selected(groups):
    result = []
    for group in groups or ['core']:
        if group not in GROUPS:
            raise LabError('可用组件组：core、mysql、redis、kafka、rocketmq；允许组合，例如 up core kafka')
        for service in GROUPS[group]:
            if service not in result:
                result.append(service)
    return result

def run(args, env=None, capture=False, timeout=60, required=True):
    try:
        result = subprocess.run(args, env=env, text=True, capture_output=capture, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise LabError(f'命令超过 {timeout} 秒；检查 Docker 状态/网络，保留现有数据后重试') from None
    except FileNotFoundError:
        raise LabError('未找到 Docker CLI。请先准备 Docker Engine + Compose v2 或 Docker Desktop，不会自动安装') from None
    if required and result.returncode:
        # 不打印命令参数或捕获的错误文本，避免把展开后的密码转到报告。
        raise LabError('Docker 命令失败；先运行 ./scripts/lab.sh doctor，再查看 logs。不会自动删除或重建数据卷')
    return result

def docker_env(config):
    # 宿主 shell 不得悄悄覆盖版本台账或激活全部 Compose profiles。
    env = {k: v for k, v in os.environ.items() if not k.startswith('COMPOSE_')}
    env.update(config)
    env.update(versions())
    return env

def compose(config, envpath):
    return ['docker', 'compose', '--project-name', config['LAB_PROJECT_NAME'],
            '--project-directory', str(INFRA), '--env-file', str(INFRA / 'versions.env'),
            '--env-file', str(envpath), '-f', str(INFRA / 'compose.yaml'), '--profile', '*']

def numeric_version(text):
    match = re.search(r'(\d+)\.(\d+)(?:\.(\d+))?', text)
    if not match:
        raise LabError('无法识别 Docker/Compose 版本，请使用正式发布版本')
    return tuple(int(x or 0) for x in match.groups())

def normalized_architecture(value):
    """只归一化本仓库已审核的两类 CPU；未知平台不能冒充已支持。"""
    return {'x86_64': 'amd64', 'amd64': 'amd64',
            'aarch64': 'arm64', 'arm64': 'arm64'}.get(str(value).lower())

def report_platform(info, env):
    """doctor 只报告显式平台覆盖，不删除变量、不改设置、不启用仿真。"""
    raw_arch = info.get('Architecture') or '未知'
    daemon_arch = normalized_architecture(raw_arch)
    print(f"Docker daemon 平台：{info.get('OSType', 'linux')}/{daemon_arch or raw_arch}（原始架构：{raw_arch}）")
    override = env.get('DOCKER_DEFAULT_PLATFORM', '')
    if not override:
        print('DOCKER_DEFAULT_PLATFORM：未设置或为空；由 Docker 按 daemon 平台选择镜像。')
    else:
        # JSON 引号转义控制字符，避免把异常环境变量当终端控制序列输出。
        print('DOCKER_DEFAULT_PLATFORM：' + json.dumps(override, ensure_ascii=False) + '（保留显式覆盖）')
        parts = override.split('/')
        override_arch = normalized_architecture(parts[1]) if len(parts) in (2, 3) else None
        if not daemon_arch or not override_arch:
            print('提醒：平台架构未识别，不能确认覆盖与 daemon 是否匹配；请核对镜像 manifest。')
        elif parts[0] != info.get('OSType', 'linux') or override_arch != daemon_arch:
            print('警告：显式平台与 Docker daemon 不匹配，可能使用仿真而更慢/占用更多资源，或无法运行；不会自动改动覆盖值。')
        else:
            print('显式平台与 Docker daemon 的系统及 CPU 架构匹配；平台变体和实际运行仍需验收。')
    if not daemon_arch:
        print('提醒：本仓库尚未审核该 daemon 架构；不能据此宣称镜像可运行。')
    print('镜像 manifest 支持不等于 Mac 实测通过；Intel/Apple Silicon 的实际运行与资源峰值仍待验收。')

def docker_ready(config):
    env = docker_env(config)
    if not shutil.which('docker'):
        raise LabError('未找到 Docker CLI：当前只能执行 verify。请按文档准备云端容器环境，勿为制作课程占用个人 Mac')
    version = run(['docker', 'compose', 'version', '--short'], env, True).stdout.strip()
    if numeric_version(version) < (2, 20, 0):
        raise LabError('需要 Compose v2.20.0 或更高；不支持旧版 docker-compose v1')
    result = run(['docker', 'info', '--format', '{{json .}}'], env, True, required=False)
    if result.returncode:
        raise LabError('Docker daemon 不可访问：启动已安装的 Docker Desktop，或检查云端 daemon/context 权限；不要使用 chmod 666 或自动 sudo')
    info = json.loads(result.stdout)
    if info.get('OSType') != 'linux':
        raise LabError('需要 Linux 容器模式')
    if numeric_version(info.get('ServerVersion', '')) < (28, 0, 0):
        raise LabError('本仓库最低基线为 Docker Engine 28.0（较旧版本可能让同网段访问回环发布端口）；升级前先核对官方系统要求')
    return info, version

def check_rocketmq_endpoint(config, envpath, container):
    """检查实时 RPC、真实 Docker 绑定及宿主 Proxy HTTP/2 往返；不冒充业务收发。"""
    env = docker_env(config)
    run(compose(config, envpath) + ['exec', '-T', 'rocketmq', 'bash',
        '/opt/lab-rocketmq/healthcheck.sh'], env, True, timeout=25)
    bindings = json.loads(run(['docker', 'inspect', '--format',
        '{{json .NetworkSettings.Ports}}', container], env, True).stdout)
    expected = {'HostIp': '127.0.0.1', 'HostPort': config['ROCKETMQ_PORT']}
    if expected not in (bindings.get('8081/tcp') or []):
        raise LabError('RocketMQ 当前发布端口与 .env 不一致；核对项目并重新 up rocketmq')
    try:
        probe_http2('127.0.0.1', int(config['ROCKETMQ_PORT']))
    except (OSError, ValueError) as exc:
        raise LabError('RocketMQ 宿主 Proxy HTTP/2 端点未就绪。检查端口/日志；远程 Docker context 的回环地址不在本机，请在 daemon 所在云主机运行入口') from exc
    state = json.loads(run(['docker', 'inspect', '--format', '{{json .State}}', container], env, True).stdout)
    if not state.get('Running') or state.get('Health', {}).get('Status') != 'healthy':
        raise LabError('RocketMQ 在端点检查期间停止或变为不健康')
    print('RocketMQ 实时管理 RPC 与宿主 Proxy HTTP/2 SETTINGS/PING 往返通过；尚不代表 gRPC 消息收发通过。')


def probe_http2(host, port):
    """无第三方依赖的明文 HTTP/2 握手；必须收到匹配 PING ACK，而非仅 TCP connect。"""
    deadline = time.monotonic() + 4
    with socket.create_connection((host, port), timeout=2) as connection:
        def read_exact(size):
            chunks = bytearray()
            while len(chunks) < size:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise ValueError('HTTP/2 响应超时')
                connection.settimeout(remaining)
                block = connection.recv(size - len(chunks))
                if not block:
                    raise ValueError('HTTP/2 连接提前关闭')
                chunks.extend(block)
            return bytes(chunks)
        connection.sendall(b'PRI * HTTP/2.0\r\n\r\nSM\r\n\r\n' + b'\x00\x00\x00\x04\x00\x00\x00\x00\x00')
        settings_seen = False
        ping = b'LABREADY'
        for _ in range(32):
            header = read_exact(9)
            length, kind, flags = int.from_bytes(header[:3], 'big'), header[3], header[4]
            stream = int.from_bytes(header[5:], 'big') & 0x7fffffff
            if length > 16384 or stream != 0:
                raise ValueError('HTTP/2 帧格式无效')
            payload = read_exact(length)
            if kind == 7:
                raise ValueError('HTTP/2 服务返回 GOAWAY')
            if kind == 4 and flags == 0 and length % 6 == 0:
                settings_seen = True
                connection.sendall(b'\x00\x00\x00\x04\x01\x00\x00\x00\x00')
                connection.sendall(b'\x00\x00\x08\x06\x00\x00\x00\x00\x00' + ping)
            elif kind == 6 and flags == 1 and payload == ping and settings_seen:
                return
        raise ValueError('HTTP/2 未返回匹配的 PING ACK')


def check_services(config, envpath, services):
    cmd, env = compose(config, envpath), docker_env(config)
    failed = []
    for service in services:
        ids = run(cmd + ['ps', '--all', '--quiet', service], env, True).stdout.split()
        if not ids:
            print(f'未启动：{service}。请运行 ./scripts/lab.sh up {service}')
            failed.append(service)
            continue
        for container in ids:
            state = json.loads(run(['docker', 'inspect', '--format', '{{json .State}}', container], env, True).stdout)
            health = state.get('Health', {}).get('Status', '无健康检查')
            running = state.get('Running', False)
            print(f"{service}: 运行={running}，健康={health}，退出码={state.get('ExitCode', '未知')}，OOM={state.get('OOMKilled', '未知')}")
            if not running or health != 'healthy':
                failed.append(service)
            elif service == 'rocketmq':
                check_rocketmq_endpoint(config, envpath, container)
    if failed:
        raise LabError('未就绪：' + '、'.join(sorted(set(failed))) + '。运行 ./scripts/lab.sh logs；首次 MySQL 初始化稍慢，先查日志，不能靠 reset 掩盖故障')
    print('容器内部协议级健康检查通过。宿主/应用连接仍须执行课程集成测试，见 runtime-contract.md。')

class ChineseParser(argparse.ArgumentParser):
    def format_help(self):
        return super().format_help().replace('usage:', '用法：')

    def format_usage(self):
        return super().format_usage().replace('usage:', '用法：')

    def error(self, message):
        self.print_help(sys.stderr)
        raise LabError('命令或参数无效，请参考上方帮助')

def parser():
    p = ChineseParser(add_help=False, usage='%(prog)s 动作 [参数...]', description='共享实验环境：默认只启动 MySQL + Redis，重型组件按需开启。')
    p._positionals.title = '位置参数'
    p._optionals.title = '选项'
    p.add_argument('-h', '--help', action='help', help='显示帮助并退出')
    p.add_argument('action', help='doctor 诊断；up 启动；check 检查；down 停止；reset 重置；build 构建；config 解析；verify 离线校验；logs 日志；images 镜像', choices=['doctor','up','check','down','reset','build','config','verify','logs','images'])
    p.add_argument('args', metavar='参数', nargs=argparse.REMAINDER, help='组件组或 build 的仓库内目录与命令')
    return p

def main(argv=None):
    if sys.version_info < (3, 9):
        raise LabError('需要 Python 3.9 或更高版本')
    args = parser().parse_args(argv)
    validate()
    action = args.action
    if action == 'verify':
        if args.args:
            raise LabError('verify 不接受额外参数')
        print('静态配置校验通过：固定镜像、回环端口、健康检查、资源边界、无特权/socket 挂载。尚未启动 Docker。')
        return 0
    if action == 'images':
        if args.args:
            raise LabError('images 不接受额外参数')
        for key, value in sorted(versions().items()):
            print(f'{key}={value}')
        return 0
    config, envpath = settings()
    if action in ('up','check','logs'):
        services = selected(args.args)
    elif action == 'reset':
        if args.args != ['--confirm-reset', config['LAB_PROJECT_NAME']]:
            raise LabError('重置会永久删除本项目 MySQL/Redis/Kafka/RocketMQ 数据及 Gradle/Maven 缓存！备份并确认项目后，显式运行 reset --confirm-reset ' + config['LAB_PROJECT_NAME'])
    elif action == 'build':
        if len(args.args) < 2:
            raise LabError('用法：build 仓库内目录 命令 参数；例如 build courses/java-recovery-collections bash ./gradlew --no-daemon test')
        directory = (ROOT / args.args[0]).resolve()
        if not directory.is_dir() or ROOT not in (directory, *directory.parents):
            raise LabError('build 目录必须真实存在且位于本仓库内，不能通过符号链接逃逸')
    elif args.args:
        raise LabError(action + ' 不接受额外参数')
    if action == 'doctor':
        print(f'脚本所在主机：{platform.system()} {platform.machine()}；Python：{platform.python_version()}（不代替 Docker daemon 架构）')
        print(f'仓库所在磁盘剩余：{shutil.disk_usage(ROOT).free / 1024**3:.1f} GiB（不是 Docker VM 的可用空间）')
    info, ver = docker_ready(config)
    if action == 'up':
        config, envpath = settings(init=True)
    cmd, env = compose(config, envpath), docker_env(config)
    if action == 'doctor':
        print(f"Docker Engine：{info['ServerVersion']}；Compose：{ver}")
        report_platform(info, env)
        print(f"Docker 分配资源：{info.get('NCPU', '?')} CPU，{info.get('MemTotal', 0) / 1024**3:.1f} GiB")
        run(cmd + ['config', '--quiet'], env)
        if info.get('MemTotal', 0) < 3 * 1024**3:
            print('提醒：Docker 少于 3 GiB，建议只开单个组件；不要并发 Java 构建与多个中间件。')
        print('已通过版本/daemon/Compose 解析检查。以下仅展示占用，不执行清理：')
        run(['docker', 'system', 'df'], env)
    elif action == 'config':
        run(cmd + ['config', '--quiet'], env)
        print('真实 Compose 配置解析通过（未输出密码，未启动容器）。')
    elif action == 'up':
        timeout = int(config['LAB_WAIT_SECONDS'])
        result = run(cmd + ['up', '--detach', '--wait', '--wait-timeout', str(timeout), '--pull', 'missing'] + services,
                     env, timeout=timeout + 600, required=False)
        if result.returncode:
            run(cmd + ['ps', '--all'], env, required=False)
            raise LabError('启动或等待就绪失败。可能是拉取受限、端口冲突、内存不足或数据版本不兼容；运行 doctor 与 logs。不会自动 reset')
        check_services(config, envpath, services)
        for service in services:
            key, _ = PORTS[service]
            print(f'{service} 的宿主入口：127.0.0.1:{config[key]}（仅此 Docker 宿主可用）')
    elif action == 'check':
        check_services(config, envpath, services)
    elif action == 'down':
        run(cmd + ['down','--timeout','30'], env, timeout=120)
        print('本项目容器与网络已停止并移除；数据卷、镜像、Gradle/Maven 缓存均保留。')
    elif action == 'reset':
        print('已收到精确项目确认，开始删除该项目容器、网络、数据卷与构建缓存。')
        run(cmd + ['down','--volumes','--timeout','30'], env, timeout=120)
        print('已重置该项目；镜像保留，其他项目未清理。')
    elif action == 'logs':
        print('以下为本机日志，可能含实验数据；分享前请脱敏。')
        run(cmd + ['logs', '--tail', '100', '--no-color'] + services, env)
        if 'rocketmq' in services:
            run(cmd + ['exec', '-T', 'rocketmq', 'bash', '/opt/lab-rocketmq/logs.sh'], env, required=False)
    elif action == 'build':
        work = '/workspace/' + directory.relative_to(ROOT).as_posix()
        print('仅启动一次性完整 JDK 21 构建容器；Gradle/Maven 缓存共享，不启动中间件。')
        result = run(cmd + ['run','--rm','--no-deps','-T','--workdir',work,'java-build'] + args.args[1:],
                     env, timeout=1800, required=False)
        return result.returncode
    return 0

if __name__ == '__main__':
    try:
        sys.exit(main())
    except (LabError, OSError, ValueError, KeyError) as exc:
        print('错误：' + str(exc), file=sys.stderr)
        sys.exit(2)
    except KeyboardInterrupt:
        print('已中断；保留现有数据。可运行 check 或 down 检查状态。', file=sys.stderr)
        sys.exit(130)
