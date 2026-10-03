#!/usr/bin/env python3
"""统一课程入口。只依赖 Python 标准库；不下载软件、不删除卷、不全局清理。"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import socket
import subprocess
import sys
import time
from urllib.parse import urlsplit

from environment_profiles import PROFILES, profile_for, topology_note

ROOT = Path(__file__).resolve().parents[1]
IMAGE_KEYS = {'MYSQL_IMAGE', 'REDIS_IMAGE', 'KAFKA_IMAGE', 'ROCKETMQ_IMAGE', 'JAVA_BUILD_IMAGE',
              'TESTCONTAINERS_RYUK_IMAGE', 'TESTCONTAINERS_TINY_IMAGE', 'JAVA_RUNTIME_IMAGE', 'KIND_NODE_IMAGE'}
TOOL_VERSION_KEYS = {'KIND_VERSION', 'KUBECTL_VERSION', 'KUBERNETES_VERSION'}
PORT_KEYS = {'mysql': 'MYSQL_PORT', 'redis': 'REDIS_PORT', 'kafka': 'KAFKA_PORT', 'rocketmq': 'ROCKETMQ_PORT'}
CONFIG_KEYS = {'LAB_PROJECT_NAME', 'MYSQL_PORT', 'REDIS_PORT', 'KAFKA_PORT', 'ROCKETMQ_PORT',
               'MYSQL_DATABASE', 'MYSQL_USER', 'MYSQL_PASSWORD', 'MYSQL_ROOT_PASSWORD', 'REDIS_PASSWORD',
               'LAB_WAIT_SECONDS', 'CAPSTONE_HTTP_PORT'}


class LabError(Exception):
    pass


def read_env(path):
    values = {}
    for number, raw in enumerate(path.read_text(encoding='utf-8').splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith('#'):
            continue
        if '=' not in line:
            raise LabError(f'{path.name} 第 {number} 行应为 KEY=VALUE')
        key, value = line.split('=', 1)
        if not re.fullmatch(r'[A-Z][A-Z0-9_]*', key) or not value or re.search(r'[\s\x00-\x1f\x7f\x22\x27`$\\]', value):
            raise LabError(f'{path.name} 第 {number} 行无效；不允许变量、引号或 shell 命令')
        if key in values:
            raise LabError(f'{path.name} 重复键 {key}')
        values[key] = value
    return values


def versions():
    path = ROOT / 'shared/versions.env'
    data = read_env(path)
    if set(data) != IMAGE_KEYS | TOOL_VERSION_KEYS:
        raise LabError('唯一镜像台账 shared/versions.env 缺键或包含未知键')
    for key, value in data.items():
        if key in TOOL_VERSION_KEYS:
            if not re.fullmatch(r'v[0-9]+[.][0-9]+[.][0-9]+', value):
                raise LabError('工具版本必须固定: ' + key)
            continue
        if not re.fullmatch(r'[a-z0-9./-]+:v?\d+\.\d+\.\d+[a-zA-Z0-9_.-]*(?:@sha256:[a-f0-9]{64})?', value):
            raise LabError(f'{key} 必须锁定完整镜像版本，不能使用 latest 或浮动标签')
    checksum = path.with_suffix('.env.sha256')
    if not checksum.is_file() or checksum.read_text().split()[0] != hashlib.sha256(path.read_bytes()).hexdigest():
        raise LabError('版本台账校验值不匹配；请恢复正确发布文件，不能静默使用其他台账')
    return data


def java_version():
    values = {}
    for line in (ROOT / 'gradle.properties').read_text(encoding='utf-8').splitlines():
        if '=' in line and not line.lstrip().startswith('#'):
            key, value = line.split('=', 1)
            values[key.strip()] = value.strip()
    value = values.get('javaVersion', '')
    if not value.isdigit():
        raise LabError('根 gradle.properties 必须声明 javaVersion；不允许另设 JDK 版本')
    return value


def config(init=False):
    path = ROOT / 'infra/.env'
    if init and not path.exists():
        # 排他创建，不覆盖学习者配置；写入前即限制权限。
        try:
            fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, 'w', encoding='utf-8') as stream:
                stream.write((ROOT / 'infra/.env.example').read_text(encoding='utf-8'))
        except FileExistsError:
            pass
    envpath = path if path.exists() else ROOT / 'infra/.env.example'
    values = read_env(envpath)
    if set(values) != CONFIG_KEYS:
        raise LabError('infra/.env 的键须与 .env.example 一致；不能在此另写镜像版本')
    name = values['LAB_PROJECT_NAME']
    if name == 'auto':
        name = 'totalacademy-' + hashlib.sha256(str(ROOT).encode()).hexdigest()[:12]
    if not re.fullmatch(r'totalacademy-[a-z0-9][a-z0-9-]{0,40}', name):
        raise LabError('LAB_PROJECT_NAME 仅允许 auto 或 totalacademy-个人后缀')
    values['LAB_PROJECT_NAME'] = name
    keys = list(PORT_KEYS.values()) + ['CAPSTONE_HTTP_PORT']
    if any(not re.fullmatch(r'[1-9][0-9]{3,4}', values[key]) or not 1024 <= int(values[key]) <= 65535 for key in keys):
        raise LabError('全部宿主端口必须为规范十进制1024–65535；不接受前导0、符号或非ASCII数字')
    if len({int(values[key]) for key in keys}) != len(keys):
        raise LabError('本课程所有宿主端口必须互不重复')
    for key in ('MYSQL_DATABASE', 'MYSQL_USER'):
        if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{0,31}', values[key]):
            raise LabError(key + ' 仅允许字母开头的字母数字及下划线，最多32字符')
    if values['MYSQL_USER'].lower() == 'root':
        raise LabError('MYSQL_USER 不能为 root')
    for key in ('MYSQL_PASSWORD', 'MYSQL_ROOT_PASSWORD', 'REDIS_PASSWORD'):
        if not re.fullmatch(r'[A-Za-z0-9_!@%+=.,:-]{12,128}', values[key]):
            raise LabError(key + ' 必须是12–128位教学密码，字符范围见文档')
    if not values['LAB_WAIT_SECONDS'].isdigit() or not 30 <= int(values['LAB_WAIT_SECONDS']) <= 900:
        raise LabError('LAB_WAIT_SECONDS 仅允许30–900秒')
    return values, envpath


def courses():
    result = json.loads((ROOT / 'authoring/course-map.json').read_text(encoding='utf-8'))
    if result.get('schema_version') not in (1, 2) or not isinstance(result.get('tasks'), list):
        raise LabError('course-map.json 格式不支持')
    seen_paths, seen_projects = set(), set()
    for task in result['tasks']:
        path = task['path']
        absolute = (ROOT / path).resolve()
        if not path or Path(path).is_absolute() or '..' in Path(path).parts or ROOT not in absolute.parents or not absolute.is_dir():
            raise LabError('课程映射题目路径缺失或越界：' + path)
        project = task['gradle_project']
        if not re.fullmatch(r':[a-zA-Z0-9_-]+', project):
            raise LabError('课程映射必须使用 Academy 原生扁平 Gradle 项目名')
        if path in seen_paths or project in seen_projects:
            raise LabError('课程映射存在重复题目或 Gradle 项目')
        seen_paths.add(path); seen_projects.add(project)
        profile_for(task)
    return result['tasks']


def task_for(value):
    matches = [task for task in courses() if value in (task['path'], task['gradle_project'])]
    if len(matches) != 1:
        raise LabError('请使用 profiles 列出的完整题目路径或 Gradle 项目名；不接受含糊简称')
    return matches[0]


def capstone_task(stage):
    matches = [task for task in courses() if task['source_course'] == 'backend-capstone'
               and task['source_task'].rsplit('/', 1)[-1] == stage]
    if len(matches) != 1:
        raise LabError('未知 capstone 阶段；请用 profiles 查看题目映射')
    return matches[0]


def execute(argv, env=None, capture=False, timeout=90, required=True, cwd=None):
    try:
        result = subprocess.run(argv, env=env, cwd=cwd, capture_output=capture, text=True, timeout=timeout)
    except FileNotFoundError:
        raise LabError('缺少所需命令；先执行 doctor。入口不会自动安装软件') from None
    except subprocess.TimeoutExpired:
        raise LabError(f'命令超过 {timeout} 秒；保留数据，请检查 status、logs 和资源占用') from None
    if required and result.returncode:
        raise LabError('命令执行失败；请查看原始输出或 logs。未自动重置数据，也未转成快测')
    return result


def environment(cfg, stage='05-defense'):
    # 显式 ledger/config 优先；禁止外部 COMPOSE_PROFILES 偷启整套服务。
    env = {key: value for key, value in os.environ.items() if not key.startswith('COMPOSE_')}
    env.update(versions()); env.update(cfg)
    env['LAB_SHARED_VERSIONS'] = str(ROOT / 'shared/versions.env')
    task = capstone_task(stage)
    env['CAPSTONE_DIST_PATH'] = str(ROOT / task['path'] / 'build/install' / task['gradle_project'][1:])
    env['CAPSTONE_STAGE'] = stage
    return env


def compose(cfg, envpath, capstone=False):
    return ['docker', 'compose', '--project-name', cfg['LAB_PROJECT_NAME'] + ('-capstone' if capstone else ''),
            '--project-directory', str(ROOT / 'infra'), '--env-file', str(ROOT / 'shared/versions.env'),
            '--env-file', str(envpath), '-f', str(ROOT / ('infra/capstone.compose.yaml' if capstone else 'infra/compose.yaml')),
            '--profile', '*']


def numeric_version(value):
    found = re.search(r'(\d+)\.(\d+)(?:\.(\d+))?', value)
    if not found:
        raise LabError('不能识别 Docker/Compose 正式版本')
    return tuple(int(part or 0) for part in found.groups())



def require_local_endpoint(value, source):
    """只允许明确本地的 Docker endpoint；不做 DNS 解析或自动回退。"""
    error = source + ' 不是明确本地Docker端点；仅允许绝对unix socket、本机npipe或精确127.0.0.1/[::1] TCP。拒绝远端/SSH/不明目标，不修改context或用户设置'
    if not isinstance(value, str) or not value or re.search(r'[\s\x00-\x1f\x7f?#]', value):
        raise LabError(error)
    # Windows 本机命名管道的唯一认可前缀；\\server\pipe 远端形式不允许。
    if re.fullmatch(r'npipe:////\./pipe/[A-Za-z0-9_.-]+', value):
        return
    try:
        parsed = urlsplit(value)
        if parsed.query or parsed.fragment or parsed.username is not None or parsed.password is not None:
            raise LabError(error)
        if (parsed.scheme == 'unix' and value.startswith('unix:///') and not parsed.netloc
                and parsed.path.startswith('/') and not parsed.path.startswith('//')
                and len(parsed.path) > 1 and '%' not in parsed.path and '\\' not in parsed.path):
            return
        if (parsed.scheme == 'tcp' and parsed.hostname in ('127.0.0.1', '::1')
                and not parsed.path and parsed.port is not None and 1 <= parsed.port <= 65535
                and re.fullmatch(r'tcp://(?:127\.0\.0\.1|\[::1\]):[1-9][0-9]{0,4}', value)):
            return
    except ValueError:
        raise LabError(error) from None
    raise LabError(error)


def require_local_daemon(env):
    """只读客户端context元数据；此门禁必须早于info、Compose和Testcontainers。"""
    host = env.get('DOCKER_HOST', '')
    if host:
        # Docker CLI可被context覆盖，而Java/Testcontainers仍可能读取DOCKER_HOST；两者独立拒绝远端。
        require_local_endpoint(host, 'DOCKER_HOST')
    selected = env.get('DOCKER_CONTEXT', '')
    if not selected:
        selected = execute(['docker', 'context', 'show'], env, capture=True).stdout.strip()
    if not isinstance(selected, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,127}', selected):
        raise LabError('不能确定安全的Docker context名称；拒绝接触daemon，不自动切换context')
    result = execute(['docker', 'context', 'inspect', '--format', '{{json .Endpoints.docker.Host}}', selected], env, capture=True)
    try:
        endpoint = json.loads(result.stdout)
    except (ValueError, TypeError):
        raise LabError('Docker context缺少可解析的Docker endpoint；拒绝接触daemon') from None
    require_local_endpoint(endpoint, 'Docker context ' + selected)
    print('本地Docker端点边界检查通过：DOCKER_HOST与选定context均未指向远端；没有切换context')


def docker_ready(env):
    require_local_daemon(env)
    version = execute(['docker', 'compose', 'version', '--short'], env, capture=True).stdout.strip()
    if numeric_version(version) < (2, 20, 0):
        raise LabError('本课程要求 Docker Compose v2.20+；不使用旧 docker-compose v1')
    result = execute(['docker', 'info', '--format', '{{json .}}'], env, capture=True, required=False)
    if result.returncode:
        raise LabError('Docker daemon 不可访问；请启动已安装的 Docker Desktop 或核对 context，不自动 sudo/改权限')
    info = json.loads(result.stdout)
    if info.get('OSType') != 'linux' or numeric_version(info.get('ServerVersion', '')) < (28, 0, 0):
        raise LabError('需 Linux 容器模式及 Docker Engine 28.0+；请参考环境文档')
    return info, version



def report_platform(info, env):
    normalize = {'aarch64': 'arm64', 'arm64': 'arm64', 'x86_64': 'amd64', 'amd64': 'amd64'}
    daemon = normalize.get(str(info.get('Architecture', '')).lower())
    override = env.get('DOCKER_DEFAULT_PLATFORM', '')
    print('DOCKER_DEFAULT_PLATFORM=' + json.dumps(override, ensure_ascii=False) + '；保留用户设置，不强制仿真')
    if override:
        parts = override.split('/')
        arch = normalize.get(parts[1]) if len(parts) in (2, 3) else None
        if not daemon or not arch:
            print('提醒：无法识别平台覆盖或 daemon 架构；不能宣称匹配')
        elif parts[0] != info.get('OSType', 'linux') or arch != daemon:
            print('警告：显式平台与 daemon 不匹配；仿真可能更慢、更占资源或无法运行，不自动更改')
    print('Apple Silicon/macOS 本次未实测；镜像支持某架构不等于实机通过')


def jdk_ready():
    major = java_version()
    home = os.environ.get('JAVA_HOME')
    prefix = Path(home) / 'bin' if home else None
    java = str(prefix / 'java') if prefix else 'java'
    javac = str(prefix / 'javac') if prefix else 'javac'
    result = execute([java, '-XshowSettings:properties', '-version'], capture=True)
    if not re.search(r'java\.specification\.version\s*=\s*' + re.escape(major) + r'\s', result.stdout + result.stderr):
        raise LabError('当前 Java 不是课程 JDK ' + major + '；请对齐 JAVA_HOME、IDEA SDK、Gradle JVM、测试 JVM')
    compiler = execute([javac, '-version'], capture=True)
    if not re.search(r'javac\s+' + re.escape(major) + r'(?:\.|\s)', compiler.stdout + compiler.stderr):
        raise LabError('需要与 Java 相同版本的完整 JDK（包括 javac）')
    print('完整 JDK ' + major + ' 检查通过；不安装或自动切换 JDK')


def validate():
    versions(); java_version(); config(); tasks = courses()
    for cap in (False, True):
        path = ROOT / ('infra/capstone.compose.yaml' if cap else 'infra/compose.yaml')
        spec = json.loads(path.read_text(encoding='utf-8'))
        expected = set(PROFILES['capstone'] if cap else PORT_KEYS)
        if set(spec['services']) != expected:
            raise LabError('Compose 服务集合与入口不一致')
        for name, service in spec['services'].items():
            if not any(re.fullmatch(r'\$\{' + key + r'(?::\?[^}]+)?\}', service['image']) for key in IMAGE_KEYS):
                raise LabError(name + ' 镜像没有引用唯一台账')
            if service.get('privileged') or service.get('network_mode') == 'host' or 'platform' in service:
                raise LabError('禁止特权、宿主网络和强制架构仿真')
            if any('docker.sock' in str(item) for item in service.get('volumes', [])):
                raise LabError('禁止把 Docker socket 挂入应用容器')
            if any(not port.startswith('127.0.0.1:') for port in service.get('ports', [])):
                raise LabError('所有发布端口必须绑定本机回环地址')
            if any(key not in service for key in ('healthcheck', 'mem_limit', 'logging')):
                raise LabError(name + ' 缺少健康检查或资源/日志边界')
    for relative in ('gradle/wrapper/gradle-wrapper.properties', 'scripts/gradle.sh', 'scripts/gradle_launcher.py', 'materials/backend-capstone/scripts/check.py',
                     'materials/backend-capstone/app/src/main/resources/static/index.html'):
        if not (ROOT / relative).is_file():
            raise LabError('发布包缺少运行文件：' + relative)
    return tasks


def owned_ids(cmd, env, services=(), running=False):
    return execute(cmd + ['ps'] + ([] if running else ['--all']) + ['--quiet'] + list(services), env, capture=True).stdout.split()


def running_services(cmd, env):
    return execute(cmd + ['ps', '--services', '--status', 'running'], env, capture=True).stdout.split()


def conflicts(cfg, envpath, env, profile, stop_others=False):
    selected = set(PROFILES[profile])
    extras = []
    for cap in (False, True):
        cmd = compose(cfg, envpath, cap)
        running = running_services(cmd, env)
        unwanted = [name for name in running if (cap != (profile == 'capstone') or name not in selected)]
        if unwanted:
            extras.append((cmd, unwanted, '-capstone' if cap else ''))
    if extras and not stop_others:
        details = '; '.join(cfg['LAB_PROJECT_NAME'] + suffix + ': ' + ','.join(names) for _, names, suffix in extras)
        raise LabError('另一个本课程 profile 仍在运行：' + details + '。如确认停止旧服务并保留卷，请重跑 start ' + profile + ' --stop-others；不会停止其他项目')
    for cmd, unwanted, _ in extras:
        execute(cmd + ['stop', '--timeout', '30'] + unwanted, env, timeout=120)
        print('已按明确选项停止旧 profile 的非共享服务；数据卷保留')


def check_ports(cfg, cmd, env, profile):
    active = set(running_services(cmd, env))
    ports = {'orders': 'CAPSTONE_HTTP_PORT'} if profile == 'capstone' else PORT_KEYS
    for name in PROFILES[profile]:
        if name not in ports or name in active:
            continue
        port = int(cfg[ports[name]])
        try:
            with socket.socket() as listener:
                listener.bind(('127.0.0.1', port))
        except OSError:
            raise LabError(f'127.0.0.1:{port} 被占用；先用 status 核对，或修改 infra/.env。不会自动结束占用进程') from None


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


def health(cmd, env, services):
    for name in services:
        ids = owned_ids(cmd, env, [name])
        if not ids:
            raise LabError(name + ' 未启动；health 不能代替 start 或课程 check')
        for cid in ids:
            state = json.loads(execute(['docker', 'inspect', '--format', '{{json .State}}', cid], env, capture=True).stdout)
            label = state.get('Health', {}).get('Status', '无健康检查')
            print(f'{name}: running={state.get("Running", False)}, health={label}, OOM={state.get("OOMKilled", False)}')
            if not state.get('Running') or label != 'healthy':
                raise LabError(name + ' 未达到协议级健康状态；检查 logs，不会 reset')
            if name == 'rocketmq':
                execute(cmd + ['exec', '-T', 'rocketmq', 'bash', '/opt/lab-rocketmq/healthcheck.sh'], env, capture=True, timeout=25)
                bindings = json.loads(execute(['docker', 'inspect', '--format', '{{json .NetworkSettings.Ports}}', cid], env, capture=True).stdout)
                expected = {'HostIp': '127.0.0.1', 'HostPort': env['ROCKETMQ_PORT']}
                if expected not in (bindings.get('8081/tcp') or []):
                    raise LabError('RocketMQ 实际发布端口与配置不一致')
                probe_http2('127.0.0.1', int(env['ROCKETMQ_PORT']))
                print('RocketMQ 管理 RPC、Proxy HTTP/2 SETTINGS 与匹配 PING ACK 通过；真实消息收发仍由完整测试验证')
    print('运行中的协议级健康检查通过；尚不等于题目判题、真实业务链或浏览器验收通过')




def verify_workbench_binding(cmd, env):
    """在业务HTTP写入前验证目标端口确实属于当前capstone的orders容器。"""
    ids = owned_ids(cmd, env, ['orders'])
    if len(ids) != 1:
        raise LabError('无法确认唯一的本课程 orders 容器；拒绝向工作台发送业务请求')
    bindings = json.loads(execute(['docker', 'inspect', '--format', '{{json .NetworkSettings.Ports}}', ids[0]], env, capture=True).stdout)
    expected = [{'HostIp': '127.0.0.1', 'HostPort': env['CAPSTONE_HTTP_PORT']}]
    if not isinstance(bindings, dict) or bindings.get('8080/tcp') != expected:
        raise LabError('本课程 orders 实际发布的127.0.0.1端口与 CAPSTONE_HTTP_PORT 不一致；可能修改了.env但尚未按原阶段重新start。拒绝创建订单、取消或replay，请先核对 status 与配置')
    state = json.loads(execute(['docker', 'inspect', '--format', '{{json .State}}', ids[0]], env, capture=True).stdout)
    if not state.get('Running') or state.get('Health', {}).get('Status') != 'healthy':
        raise LabError('本课程 orders 在绑定检查期间停止或不健康；拒绝发送业务请求')
    print('已核对本课程 orders 的实际回环端口绑定；业务请求只使用这一配置端点')


def wait_existing_health(cmd, env, service, container_id, timeout):
    """只等待已经存在的本课程容器；不换检查点、不重建挂载或重置数据。"""
    deadline = time.monotonic() + timeout
    while True:
        state = json.loads(execute(['docker', 'inspect', '--format', '{{json .State}}', container_id], env, capture=True).stdout)
        if state.get('Running') and state.get('Health', {}).get('Status') == 'healthy':
            health(cmd, env, [service])
            return
        if state.get('OOMKilled') or state.get('Dead') or (not state.get('Running') and state.get('ExitCode', 0) != 0):
            raise LabError(service + ' 恢复后退出或OOM；查看 logs，不会重新建卷或换检查点')
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise LabError(service + ' 恢复健康等待超时；保留容器和卷，请查看 logs')
        time.sleep(min(2, remaining))


def operate_capstone_service(action, cmd, env, service, timeout):
    """只操作 Compose 精确项目中现有的一个服务，不认领其他项目。"""
    ids = owned_ids(cmd, env, [service])
    if len(ids) != 1:
        raise LabError('未找到唯一的本课程 ' + service + ' 容器；先 start capstone --stage 当前检查点，不在故障操作中创建新环境')
    if action == 'pause-service':
        execute(cmd + ['stop', '--timeout', '30', service], env, timeout=120)
        print(service + ' 已安全停止；本课程容器、原检查点挂载和数据卷保留')
    elif action == 'crash-service':
        if service not in ('orders', 'delivery'):
            raise LabError('强制崩溃仅允许 orders/delivery')
        execute(cmd + ['kill', '--signal', 'SIGKILL', service], env)
        print(service + ' 已执行显式 SIGKILL 故障注入；不代表优雅关闭，数据卷保留')
    else:
        # docker start 恢复同一个容器，避免 compose up 按默认stage重建成另一阶段。
        execute(['docker', 'start', ids[0]], env)
        wait_existing_health(cmd, env, service, ids[0], timeout)
        print(service + ' 已恢复同一容器并通过协议级健康检查；原检查点/卷未替换，请继续完整业务恢复检查')


def check_plan(task):
    project = task['gradle_project']
    commands = [project + ':test']
    # 不以 unitTest、跳过集成或缺 Docker 的绿色状态替代真实 gates。
    integrated_in_test = (task['source_course'] == 'distributed-systems'
                          and task['source_task'].rsplit('/', 1)[-1] in ('06-transactions', '07-outbox-cache'))
    if not integrated_in_test and (task['source_course'] == 'backend-capstone'
                                  or any((ROOT / task['path'] / 'integration-test').rglob('*.java'))):
        commands.append(project + ':integrationTest')
    return ['bash', str(ROOT / 'scripts/gradle.sh'), '--no-daemon', '--max-workers=1'] + commands + (['-PwithDocker'] if task['source_course'] == 'messaging' else [])


def resources(cfg, envpath, env):
    ids = []
    for cap in (False, True):
        ids += owned_ids(compose(cfg, envpath, cap), env, running=True)
    print(f'课程目录所在磁盘剩余 {shutil.disk_usage(ROOT).free / 1024**3:.1f} GiB；此数不是 Docker VM 可用空间')
    if ids:
        execute(['docker', 'stats', '--no-stream'] + ids, env)
    else:
        print('本课程没有正在运行的 Compose 容器；测试临时容器不计入此列表')
    print('以下是 Docker 全局只读占用（包含其他项目，不执行清理）：')
    execute(['docker', 'system', 'df'], env)


def parser():
    p = argparse.ArgumentParser(description='一个课程的按需环境入口。默认不启动、不下载任何镜像。', usage='%(prog)s 动作 [目标] [选项]')
    p.add_argument('action', nargs='?', default='help', choices=['help', 'verify', 'images', 'profiles', 'doctor', 'start', 'stop', 'status', 'resources', 'resourceusage', 'health', 'check', 'workbench-check', 'logs', 'pause-service', 'recover-service', 'crash-service'])
    p.add_argument('target', nargs='?', help='环境 profile；check 时须为完整题目路径或 Gradle 项目名')
    p.add_argument('--service', choices=PROFILES['capstone'], help='仅capstone故障操作使用；限定本课程mysql/redis/kafka/delivery/orders')
    p.add_argument('--stage', default='05-defense', help='capstone 检查点，默认05-defense；须已完成该节练习')
    p.add_argument('--stop-others', action='store_true', help='确认仅停止本课程旧 profile 非共享服务，保留卷；仅 start 可用')
    p.add_argument('--dry-run', action='store_true', help='仅显示 check 命令，绝不冒充判题通过')
    return p


def main(argv=None):
    if sys.version_info < (3, 9):
        raise LabError('需要 Python 3.9+')
    p = parser(); args = p.parse_args(argv)
    if args.action == 'help':
        p.print_help(); return 0
    service_action = args.action in ('pause-service', 'recover-service', 'crash-service')
    if args.service and not service_action:
        raise LabError('--service 只用于 capstone 的 pause-service/recover-service/crash-service')
    if service_action and (args.target != 'capstone' or not args.service):
        raise LabError('故障操作须明确指定 capstone 与 --service 白名单服务')
    if args.action == 'crash-service' and args.service not in ('orders', 'delivery'):
        raise LabError('强制崩溃仅允许本课程 orders 或 delivery；数据库/MQ只允许安全停止和恢复')
    if args.stop_others and args.action != 'start':
        raise LabError('--stop-others 只用于 start')
    if args.dry_run and args.action != 'check':
        raise LabError('--dry-run 只用于 check')
    tasks = validate()
    if args.action in ('verify', 'images', 'profiles'):
        if args.target:
            raise LabError(args.action + ' 不接受目标参数')
        if args.action == 'verify':
            print('静态环境/路径/镜像台账校验通过；没有运行 Java、Docker、真实判题或 GUI')
        elif args.action == 'images':
            for key, value in sorted(versions().items()): print(key + '=' + value)
        else:
            print('手动 profile：' + '、'.join(PROFILES))
            for task in tasks:
                print(f'{task["path"]} -> {profile_for(task)} -> {task["gradle_project"]}')
                note = topology_note(task)
                if '仅' in note or '依次' in note: print('  ' + note)
        return 0
    if args.action == 'check':
        if not args.target: raise LabError('check 必须选择一个完整题目路径，避免一次启动全部课程测试')
        task = task_for(args.target); command = check_plan(task)
        print('完整判题计划：' + ' '.join(command))
        print(topology_note(task))
        if args.dry_run:
            print('仅展示计划；未运行判题，不构成通过证据'); return 0
        jdk_ready()
        cfg, envpath = config(); env = environment(cfg, args.stage)
        if profile_for(task) != 'java':
            docker_ready(env)
            if any(running_services(compose(cfg, envpath, cap), env) for cap in (False, True)):
                raise LabError('为避免重复占用，完整容器测试前请先执行 stop all；保留演示卷，Testcontainers 自建隔离服务')
        result = execute(command, env, timeout=7200, required=False, cwd=ROOT)
        if result.returncode:
            print('完整判题失败；请修正题目或环境。未改为 unitTest，未跳过真实服务', file=sys.stderr)
        return result.returncode
    profile = args.target or ('all' if args.action in ('stop', 'status', 'logs') else 'java')
    if profile not in PROFILES and not (profile == 'all' and args.action in ('stop', 'status', 'logs')):
        raise LabError('未知 profile；运行 profiles 查看。start 必须显式选择所需组件')
    if args.action == 'workbench-check' and profile != 'capstone':
        raise LabError('workbench-check 只接受 capstone')
    if args.action in ('stop', 'status', 'logs') and profile == 'java':
        print('java profile 没有常驻容器；不调用 Compose，不停止或读取其他 profile 的服务')
        return 0
    if args.action in ('start', 'health') and profile == 'java':
        jdk_ready(); print('此 profile 不需要常驻中间件；执行 check 题目路径判题'); return 0
    cfg, envpath = config(init=args.action == 'start')
    env = environment(cfg, args.stage)
    if args.action == 'doctor':
        jdk_ready()
        print(f'主机 {platform.system()} {platform.machine()}；Python {platform.python_version()}；项目 {cfg["LAB_PROJECT_NAME"]}')
        if profile == 'java':
            print('java profile 无需 Docker；需要真实数据库/MQ 时运行 doctor mysql 等所需 profile 诊断')
            print('Apple Silicon/macOS 本次未实测；当前 doctor 仅检查本机实际工具，不代表课程端到端通过')
            return 0
    info, ver = docker_ready(env)
    if args.action == 'doctor':
        print(f'Docker Engine {info["ServerVersion"]}；Compose {ver}；daemon 架构 {info.get("Architecture", "未知")}')
        print(f'Docker 资源 {info.get("NCPU", "未知")} CPU，{info.get("MemTotal", 0) / 1024**3:.1f} GiB')
        report_platform(info, env)
        for cap in (False, True): execute(compose(cfg, envpath, cap) + ['config', '--quiet'], env)
        resources(cfg, envpath, env)
        return 0
    if args.action in ('resources', 'resourceusage'):
        resources(cfg, envpath, env); return 0
    cap = profile == 'capstone'; cmd = compose(cfg, envpath, cap)
    if service_action:
        operate_capstone_service(args.action, cmd, env, args.service, int(cfg['LAB_WAIT_SECONDS']))
        return 0
    if args.action == 'start':
        spec = json.loads((ROOT / ('infra/capstone.compose.yaml' if cap else 'infra/compose.yaml')).read_text())
        total_mib = sum(int(spec['services'][name]['mem_limit'].removesuffix('m')) for name in PROFILES[profile])
        print(f'所选常驻容器内存上限合计 {total_mib} MiB；不是实测峰值，另需为 Docker VM、IDEA、JDK 与构建留空间')
        if info.get('MemTotal', 0) < (total_mib + 512) * 1024**2:
            print('提醒：Docker 分配内存接近或低于本 profile 容器预算；建议先停止其他实验，检查资源设置后再运行')
        conflicts(cfg, envpath, env, profile, args.stop_others)
        check_ports(cfg, cmd, env, profile)
        if cap:
            jdk_ready(); task = capstone_task(args.stage)
            execute(['bash', str(ROOT / 'scripts/gradle.sh'), '--no-daemon', '--max-workers=1', task['gradle_project'] + ':installDist'], env, timeout=1800, cwd=ROOT)
            if not (Path(env['CAPSTONE_DIST_PATH']) / 'lib').is_dir():
                raise LabError('Gradle 未生成预期阶段分发 lib 目录；拒绝启动空挂载')
        timeout = int(cfg['LAB_WAIT_SECONDS'])
        execute(cmd + ['up', '--detach', '--wait', '--wait-timeout', str(timeout), '--pull', 'missing'] + list(PROFILES[profile]), env, timeout=timeout+600)
        health(cmd, env, PROFILES[profile])
        if cap: print('预置中文工作台：http://127.0.0.1:' + cfg['CAPSTONE_HTTP_PORT'] + '；无需安装 Node 或另建前端')
        else:
            for name in PROFILES[profile]: print(name + '：127.0.0.1:' + cfg[PORT_KEYS[name]])
    elif args.action in ('stop', 'status', 'logs'):
        for is_cap in ((False, True) if profile == 'all' else (cap,)):
            current = compose(cfg, envpath, is_cap)
            names = [] if profile == 'all' else list(PROFILES[profile])
            action = {'stop': ['stop', '--timeout', '30'], 'status': ['ps', '--all'], 'logs': ['logs', '--tail', '100', '--no-color']}[args.action]
            execute(current + action + names, env, timeout=120)
        if args.action == 'stop': print('仅停止所选本课程容器；容器、数据卷、镜像与构建缓存均保留；没有执行清理')
    elif args.action == 'health': health(cmd, env, PROFILES[profile])
    elif args.action == 'workbench-check':
        health(cmd, env, PROFILES['capstone'])
        verify_workbench_binding(cmd, env)
        print('工作台业务检查会创建并取消一个带唯一编号的教学订单；不清空已有数据')
        return execute([sys.executable, str(ROOT / 'materials/backend-capstone/scripts/check.py')], env, timeout=300, required=False).returncode
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (LabError, OSError, ValueError, KeyError, TypeError) as exc:
        print('错误：' + str(exc), file=sys.stderr)
        sys.exit(2)
    except KeyboardInterrupt:
        print('已中断；保留现有数据。请查看 status 再按需 stop', file=sys.stderr)
        sys.exit(130)
