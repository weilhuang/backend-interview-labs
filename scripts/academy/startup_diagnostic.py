#!/usr/bin/env python3
"""只诊断固定 Academy 的 fresh-profile GUI 初始化，绝不签发课程验收结果。"""
from __future__ import annotations
import argparse
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import select
import shutil
import signal
import struct
import subprocess
import time
import xml.etree.ElementTree as ET
import zipfile

from safe_io import (BoundaryError, absolute, directory_fd, exclusive_writer, new_directory,
                     read_regular, regular_reader, replace_regular, validate_directory, write_new)
from run_official import cli_environment, sanitized_environment
from collect_evidence import sanitize_text

MAX_SECONDS = 180
RESERVE_SECONDS = 15
REPORT_RESERVE_SECONDS = 3
LOG_LIMIT = 256 * 1024
DUMP_LIMIT = 512 * 1024
PNG_LIMIT = 4 * 1024 * 1024
MIN_FREE = 2 * 1024**3
EXPECTED_EXIT = 20
# 厂商配置读取与证据输出分开；固定归档实测 product-info 为319506字节，SHA已核。
METADATA_LIMITS = {'toolchain_pins': 65536, 'idea_product_info': 512 * 1024,
                   'helper_jdk_release': 65536, 'idea_jbr_release': 65536}
FIXED_PRODUCT_INFO_SHA256 = '9a051df5f04c52a12252f6f61ea414836b125530a4f43110bcd29fde51c9cb7f'
OUTCOMES = {'EXPECTED_INPUT_ERROR_NOT_ACCEPTANCE': 20, 'UNRESOLVED_TIMEOUT': 21,
            'UNEXPECTED_EXIT': 22, 'PREFLIGHT_OR_COLLECTION_ERROR': 23,
            'OWNERSHIP_UNVERIFIED': 24}


class OwnershipError(ValueError):
    """归属无法建立时只报告失败，绝不尝试数字 PID 清理。"""


def require(ok, message):
    if not ok:
        raise ValueError(message)


def check_deadline(deadline):
    if time.monotonic() >= deadline:
        raise TimeoutError('本次协作式截止时间已到；不再开始扫描、采集或信号操作')


def record(path, value):
    replace_regular(path, (json.dumps(value, indent=2, ensure_ascii=False) + '\n').encode())


def checked_root(root, runner_temp, excluded):
    root = absolute(root)
    temp = absolute(runner_temp)
    validate_directory(temp)
    validate_directory(root.parent)
    require(root != temp and root.is_relative_to(temp), '诊断目录必须是 RUNNER_TEMP 的新子目录')
    require(not root.exists() and not root.is_symlink(), '不能复用诊断目录')
    for other in excluded:
        other = absolute(other)
        validate_directory(other)
        require(not root.is_relative_to(other) and not other.is_relative_to(root), '诊断目录与输入目录重叠')
    return root


def confirm_absent(path):
    with directory_fd(path.parent) as parent:
        try:
            os.stat(path.name, dir_fd=parent, follow_symlinks=False)
        except FileNotFoundError:
            return
    raise ValueError('诊断输入必须不存在，包括悬空符号链接')


def diagnostic_command(idea, root):
    missing = root / 'intentionally-missing-diagnostic-course.zip'
    target = root / 'diagnostic-target'
    report = root / 'never-an-acceptance-report.json'
    for path in (missing, target, report):
        confirm_absent(path)
    return [str(idea / 'bin/idea'), 'validateCourse', str(target), '--archive', str(missing),
            '--tests', 'false', '--links', 'false', '--output-format', 'json', '--output', str(report)]


def classify(returncode, timed_out, texts, missing, report_exists, missing_exists):
    # 只认可官方 archive-load 错误文本与正常非零退出的组合。普通帮助或 args 回显不算。
    marker = 'Failed to create course object from `' + str(missing) + '` archive'
    if (returncode == 1 and not timed_out and marker in '\n'.join(texts)
            and not report_exists and not missing_exists):
        return 'EXPECTED_INPUT_ERROR_NOT_ACCEPTANCE'
    return 'UNRESOLVED_TIMEOUT' if timed_out else 'UNEXPECTED_EXIT'


def parse_stat(raw):
    # comm 可包含空格和括号；最后一个右括号之后才是固定字段。
    fields = raw[raw.rfind(')') + 2:].split()
    return {'state': fields[0], 'ppid': int(fields[1]), 'pgrp': int(fields[2]),
            'session': int(fields[3]), 'start': int(fields[19])}


def proc_identity(pid):
    base = Path('/proc') / str(pid)
    before = parse_stat(read_regular(base / 'stat', 8192).decode())
    uid = base.stat().st_uid
    after = parse_stat(read_regular(base / 'stat', 8192).decode())
    require(before['start'] == after['start'], '进程身份读取时改变')
    return {**after, 'uid': uid, 'pid': pid}


def same_owner(initial, current):
    return all(initial[k] == current[k] for k in ('pid', 'start', 'uid', 'session', 'pgrp'))


@dataclass
class OwnedPid:
    identity: dict
    fd: int

    @classmethod
    def open(cls, pid, session, parent=None):
        before = proc_identity(pid)
        require(before['uid'] == os.getuid() and before['session'] == session,
                '拒绝非本次会话或非本用户进程')
        if parent is not None:
            require(before['ppid'] == parent, '子进程父身份不符')
        fd = os.pidfd_open(pid)
        try:
            after = proc_identity(pid)
            require(same_owner(before, after), '打开 pidfd 时进程归属改变')
            return cls(after, fd)
        except BaseException:
            os.close(fd)
            raise

    def current(self):
        # pidfd 可读表示原进程已退出；即使数字 PID 再出现也不会跟随。
        if select.select([self.fd], [], [], 0)[0]:
            return None
        try:
            current = proc_identity(self.identity['pid'])
        except FileNotFoundError:
            if select.select([self.fd], [], [], 0)[0]:
                return None
            raise
        require(same_owner(self.identity, current), '进程归属或会话已改变')
        return current

    def send(self, sig, deadline):
        check_deadline(deadline)
        current = self.current()
        check_deadline(deadline)
        if current is not None:
            # 只向 pidfd 发信号，永远不调用 killpg 或数字 PID 的 kill。
            try:
                signal.pidfd_send_signal(self.fd, sig)
            except ProcessLookupError:
                pass  # 原进程在最后一次复核后正常退出，pidfd 不会转向复用 PID。

    def close(self):
        os.close(self.fd)


class Child:
    """保留直接子进程的 pidfd；只沿已核验的后代树登记有限数量的进程。"""
    def __init__(self, command, env, cwd, out, err, pass_fds=()):
        self.handles = []
        self.out, self.err = out, err
        with exclusive_writer(out) as stdout, exclusive_writer(err) as stderr:
            self.proc = subprocess.Popen(command, env=env, cwd=cwd, stdout=stdout, stderr=stderr,
                                         start_new_session=True, pass_fds=pass_fds)
        # 直接子进程在本对象 poll/wait 之前不会被本父进程回收或复用。
        try:
            self.handles.append(OwnedPid.open(self.proc.pid, self.proc.pid))
        except (OSError, ValueError) as exc:
            raise OwnershipError('子进程已启动但归属登记失败；未对未核验 PID 发信号，需 runner 销毁回收') from exc

    def discover(self, deadline):
        check_deadline(deadline)
        seen = {item.identity['pid'] for item in self.handles}
        for item in self.handles:
            check_deadline(deadline)
            current = item.current()
            check_deadline(deadline)
            if current is None:
                continue
            base = Path('/proc') / str(current['pid']) / 'task'
            tids = sorted(base.iterdir(), key=lambda path: int(path.name))
            check_deadline(deadline)
            require(len(tids) <= 1024, '本次进程线程目录超过观察上限')
            for task in tids:
                check_deadline(deadline)
                try:
                    children = read_regular(task / 'children', 16384).decode().split()
                except FileNotFoundError:
                    continue
                check_deadline(deadline)
                # 没有枚举系统 /proc、其他进程、environ、全局窗口或用户 profile。
                for value in children:
                    check_deadline(deadline)
                    pid = int(value)
                    if pid in seen:
                        continue
                    require(len(self.handles) < 128, '本次子进程树超过观察上限')
                    try:
                        child = OwnedPid.open(pid, self.proc.pid, current['pid'])
                        if item.current() is None:
                            child.close()
                            raise ValueError('登记后代时父进程退出')
                    except ProcessLookupError:
                        continue
                    except FileNotFoundError:
                        continue
                    self.handles.append(child)
                    seen.add(pid)
                    check_deadline(deadline)
        check_deadline(deadline)

    def alive(self):
        return self.handles[0].current() is not None

    def stop(self, deadline):
        failures = []
        if time.monotonic() >= deadline:
            return ['清理截止时间已到；未扫描或发送信号，未核验遗留由本次 runner 回收']
        try:
            self.discover(deadline)
        except TimeoutError:
            return ['清理发现阶段到达截止时间；不再发送信号']
        except (OSError, ValueError) as exc:
            failures.append(type(exc).__name__)
        for sig, grace in ((signal.SIGTERM, 4), (signal.SIGKILL, 1)):
            for item in reversed(self.handles):
                try:
                    item.send(sig, deadline)
                except TimeoutError:
                    return failures + ['清理信号阶段到达截止时间；不再发送信号']
                except (OSError, ValueError) as exc:
                    failures.append(type(exc).__name__)
            until = min(deadline, time.monotonic() + grace)
            while time.monotonic() < until:
                if all(select.select([item.fd], [], [], 0)[0] for item in self.handles):
                    break
                time.sleep(.05)
        # wait 只回收自己直接启动的根进程；信号发送不依赖可复用 PID。
        if time.monotonic() >= deadline:
            return failures + ['清理确认阶段到达截止时间；未继续等待']
        if select.select([self.handles[0].fd], [], [], 0)[0]:
            self.proc.wait(timeout=0)
        else:
            failures.append('根进程未确认退出')
        return failures

    def close(self):
        for item in self.handles:
            item.close()


def checked_jvm(child, idea, deadline):
    # 仅支持本父进程尚未回收的直接 IDEA 子进程。若启动器另 fork JVM，诚实标记不可采集。
    check_deadline(deadline)
    current = child.handles[0].current()
    require(current is not None, 'IDE 已退出')
    pid = current['pid']
    base = Path('/proc') / str(pid)
    executable = Path(os.readlink(base / 'exe'))
    require(executable in {idea / 'bin/idea', idea / 'jbr/bin/java'}, 'IDE 可执行文件不属于固定工具链')
    command = read_regular(base / 'cmdline', 65536).split(b'\0')
    require(b'validateCourse' in command, '直接子进程不是 validateCourse')
    maps = read_regular(base / 'maps', 2 * 1024 * 1024).decode(errors='replace')
    check_deadline(deadline)
    require(any(line.rstrip().endswith(str(idea / 'jbr/lib/server/libjvm.so')) for line in maps.splitlines()),
            '未发现该固定 JBR 的 libjvm 映射')
    require(child.handles[0].current() is not None, '采集前 IDE 已退出')
    check_deadline(deadline)
    # 此后至 jcmd 退出不 poll/wait 该 IDEA：即使 IDEA 退出也保持僵尸 PID，杜绝 attach 到复用 PID。
    return pid


def xauthority_bytes():
    # 本次 Xvfb 的临时 MIT cookie；不写入报告，不复制到 artifact，不继承外部 Xauthority。
    # FamilyWild 的字段格式与 xauth nmerge 一致；仅本次私有文件供 server/client 使用。
    fields = (b'', b'', b'MIT-MAGIC-COOKIE-1', secrets.token_bytes(16))
    return struct.pack('!H', 65535) + b''.join(struct.pack('!H', len(field)) + field for field in fields)


def read_preflight_metadata(path, label, observations):
    """同一 no-follow 普通文件描述符度量/读取/哈希，只记录标签和非敏感文件元数据。"""
    require(label in METADATA_LIMITS, '未知预检metadata标签')
    limit = METADATA_LIMITS[label]
    item = {'label': label, 'limit_bytes': limit, 'status': 'OPENING'}
    observations.append(item)
    try:
        with regular_reader(path) as stream:
            before = os.fstat(stream.fileno())
            item['size_bytes'] = before.st_size
            if before.st_size > limit:
                item['status'] = 'REJECTED_SIZE'
                raise BoundaryError(f'预检metadata超界：label={label}, size_bytes={before.st_size}, limit_bytes={limit}')
            data = stream.read(limit + 1)
            after = os.fstat(stream.fileno())
            item['size_after_bytes'] = after.st_size
            item['read_bytes'] = len(data)
            identity = ('st_dev', 'st_ino', 'st_size', 'st_mtime_ns', 'st_ctime_ns')
            if (len(data) > limit or len(data) != before.st_size
                    or any(getattr(before, key) != getattr(after, key) for key in identity)):
                item['status'] = 'REJECTED_CHANGED_FILE'
                raise BoundaryError('预检metadata读取期间改变：label=' + label)
            item['sha256'] = hashlib.sha256(data).hexdigest()
            if label == 'idea_product_info' and item['sha256'] != FIXED_PRODUCT_INFO_SHA256:
                item['status'] = 'REJECTED_FIXED_HASH'
                raise BoundaryError('固定官方product-info SHA256不符：label=' + label)
            item['status'] = 'READ_FIXED_HASH_VERIFIED' if label == 'idea_product_info' else 'READ_HASH_RECORDED'
            return data
    except (OSError, ValueError):
        if item['status'] == 'OPENING':
            item['status'] = 'UNAVAILABLE'
        raise


def preflight(idea, plugins, root, observations=None):
    require(os.environ.get('GITHUB_ACTIONS') == 'true' and os.environ.get('RUNNER_ENVIRONMENT') == 'github-hosted',
            '仅允许新的 GitHub-hosted CI runner；禁止个人工作站或 self-hosted runner')
    observations = [] if observations is None else observations
    pins = json.loads(read_preflight_metadata(Path(__file__).with_name('toolchain.json'), 'toolchain_pins', observations))
    require(pins['idea']['build'] == '261.27258.48' and pins['academy']['version'] == '2026.9-2026.1-1070',
            '候选只允许已批准固定版本')
    info = json.loads(read_preflight_metadata(idea / 'product-info.json', 'idea_product_info', observations))
    require((info['productCode'], info['version'], info['buildNumber']) ==
            ('IU', pins['idea']['version'], pins['idea']['build']), 'IDE 身份不符')
    jar = plugins / 'JetBrainsAcademy/lib' / ('JetBrainsAcademy-' + pins['academy']['version'] + '.jar')
    with regular_reader(jar) as source, zipfile.ZipFile(source) as archive:
        metadata = ET.fromstring(archive.read('META-INF/plugin.xml'))
    require(metadata.findtext('id') == 'com.jetbrains.edu' and metadata.findtext('version') == pins['academy']['version'],
            'Academy 身份不符')
    java = Path(os.environ.get('JAVA_HOME', '/nonexistent')).resolve()
    helper_release = read_preflight_metadata(java / 'release', 'helper_jdk_release', observations).decode()
    require(re.search(r'^JAVA_VERSION="21(?:[."+])', helper_release, re.M),
            'Robot helper 必须使用现有 Java 21')
    for binary in (idea / 'bin/idea', java / 'bin/java'):
        require(binary.is_file() and os.access(binary, os.X_OK), '所需已有可执行文件不可用')
    xvfb = shutil.which('Xvfb')
    require(xvfb is not None, '缺少已有 Xvfb；本候选不安装依赖')
    require(hasattr(os, 'pidfd_open') and hasattr(signal, 'pidfd_send_signal'), '需要 Linux pidfd 支持')
    descriptor = os.pidfd_open(os.getpid())
    os.close(descriptor)
    require(signal.getsignal(signal.SIGCHLD) == signal.SIG_DFL, 'SIGCHLD 策略不支持防复用直接子进程')
    require(shutil.disk_usage(root).free >= MIN_FREE, '诊断启动前空间不足')
    jcmd = idea / 'jbr/bin/jcmd'
    metadata = {}
    releases = {'helper_jdk': helper_release, 'idea_jbr': read_preflight_metadata(idea / 'jbr/release', 'idea_jbr_release', observations).decode()}
    for name, raw in releases.items():
        metadata[name] = {key: value for key, value in re.findall(r'^(JAVA_VERSION|JAVA_RUNTIME_VERSION|IMPLEMENTOR|IMPLEMENTOR_VERSION)="([^"]+)"$', raw, re.M)}
    metadata['tool_paths'] = {'java': str(java / 'bin/java'), 'jcmd': str(jcmd),
                              'Xvfb': xvfb, 'xwininfo': shutil.which('xwininfo')}
    metadata['version_scope'] = 'IDE/Academy归档固定；JDK21仅固定major，X11工具来自runner镜像，未声称全部依赖字节固定'
    return {'xvfb': xvfb, 'java': java / 'bin/java', 'runtime_metadata': metadata,
            'jcmd': jcmd if jcmd.is_file() and os.access(jcmd, os.X_OK) else None,
            'xwininfo': shutil.which('xwininfo'), 'pins': pins}


def isolated_environment(idea, plugins, root):
    """定向已知 profile/home/tmp 设置；这是配置隔离，不是文件系统沙箱。"""
    env, profile = cli_environment(idea, plugins, root, 'diagnostic')
    for key in ('DISPLAY', 'XAUTHORITY'):
        env.pop(key, None)
    env.update(HOME=str(root / 'home'), XDG_CONFIG_HOME=str(root / 'xdg-config'),
               XDG_CACHE_HOME=str(root / 'xdg-cache'), XDG_DATA_HOME=str(root / 'xdg-data'),
               TMPDIR=str(profile / 'tmp'))
    options = profile / 'idea.vmoptions'
    lines = read_regular(options, 256 * 1024).decode().splitlines()
    lines = [line for line in lines if not line.startswith('-Duser.home=')]
    replace_regular(options, ('\n'.join([*lines, '-Duser.home=' + str(root / 'home')]) + '\n').encode())
    return env


class Probe:
    def __init__(self, root, env, seconds, started=None):
        self.root, self.env = root, env
        self.started = time.monotonic() if started is None else started
        self.deadline = self.started + seconds
        self.cutoff = self.deadline - RESERVE_SECONDS
        self.cleanup_deadline = self.deadline - REPORT_RESERVE_SECONDS
        self.children = []
        self.summary = {'schema_version': 1, 'scope': 'GUI_STARTUP_DIAGNOSTIC_ONLY',
                        'outcome': 'PREFLIGHT_OR_COLLECTION_ERROR', 'native_tests': 'NOT_RUN',
                        'links': 'NOT_RUN', 'acceptance_pass': False, 'release_allowed': False,
                        'budget_seconds': seconds, 'cleanup_reserve_seconds': RESERVE_SECONDS,
                        'budget_kind': 'COOPERATIVE_TARGET_NOT_HARD_REALTIME',
                        'report_reserve_seconds': REPORT_RESERVE_SECONDS,
                        'workflow_step_timeout_seconds': 240,
                        'filesystem_sandbox': False,
                        'cleanup_scope': '只核验已登记且归属未改变的进程；未登记或脱离会话的后代交给本次 runner 销毁回收',
                        'full_process_tree_exit_verified': False,
                        'metadata_reads': [],
                        'observations': [], 'cleanup_errors': []}

    def launch(self, command, label, pass_fds=()):
        check_deadline(self.cutoff)
        child = Child(command, self.env, self.root, self.root / 'raw' / (label + '.stdout'),
                      self.root / 'raw' / (label + '.stderr'), pass_fds)
        self.children.append(child)
        check_deadline(self.cutoff)
        return child

    def tick(self):
        check_deadline(self.cutoff)
        require(shutil.disk_usage(self.root).free >= MIN_FREE, '诊断空间下限触发')
        for child in self.children:
            child.discover(self.cutoff)
            check_deadline(self.cutoff)
            for path in (child.out, child.err):
                require(path.stat().st_size <= 2 * 1024 * 1024, '单条诊断输出超过资源上限')
                check_deadline(self.cutoff)
        # 只检查固定 idea.log，不遍历 profile/cache；整机临时空间由上述余量守卫覆盖。
        log = self.root / 'diagnostic-profile/log/idea.log'
        if log.exists():
            require(log.stat().st_size <= 8 * 1024 * 1024, '本次 IDE 日志超过资源上限')
        check_deadline(self.cutoff)

    def run_tool(self, command, label, seconds):
        child = self.launch(command, label)
        until = min(self.cutoff, time.monotonic() + seconds)
        while child.alive() and time.monotonic() < until:
            self.tick()
            time.sleep(.1)
        timed_out = child.alive()
        if timed_out:
            self.summary['cleanup_errors'].extend(child.stop(min(self.cutoff, time.monotonic() + 5)))
        else:
            child.proc.wait(timeout=0)
        return child, {'exit_code': child.proc.returncode, 'timed_out': timed_out}

    def evidence_text(self, source, name, limit, deadline=None):
        deadline = self.cutoff if deadline is None else deadline
        check_deadline(deadline)
        data = read_regular(source, limit, tail=True)
        text = sanitize_text(data.decode('utf8', errors='replace'))
        check_deadline(deadline)
        write_new(self.root / 'evidence' / name, text.encode()[:limit].decode('utf8', errors='ignore').encode())
        check_deadline(deadline)
        return text

    def display(self, tools):
        auth = self.root / 'private-xauthority'
        write_new(auth, xauthority_bytes())
        self.env['XAUTHORITY'] = str(auth)
        readfd, writefd = os.pipe()
        try:
            server = self.launch([tools['xvfb'], '-displayfd', str(writefd), '-screen', '0', '1280x900x24',
                                  '-nolisten', 'tcp', '-auth', str(auth)], 'xvfb', (writefd,))
        finally:
            os.close(writefd)
        try:
            ready, _, _ = select.select([readfd], [], [], min(8, max(0, self.cutoff - time.monotonic())))
            require(ready, '专用 Xvfb 未在预算内就绪')
            raw = os.read(readfd, 32)
            require(re.fullmatch(rb'\d+\n', raw) is not None and server.alive(), '专用 Xvfb 返回无效 display')
            check_deadline(self.cutoff)
            self.env['DISPLAY'] = ':' + raw.decode().strip()
        finally:
            os.close(readfd)
        self.server = server

    def observe(self, ide, idea, tools):
        require(self.server.alive(), '专用 Xvfb 已退出；禁止读取替代 display')
        self.summary['observations'].append({'kind': 'screen', 'at_seconds': round(time.monotonic() - self.started, 2)})
        screen = self.summary['observations'][-1]
        helper = Path(__file__).with_name('probes') / 'StartupScreen.java'
        # 源文件模式运行 JDK21 标准 Robot；不是向 IDE 注入 agent，也不更换 IDEA 的 JBR。
        child, status = self.run_tool([str(tools['java']), '-Duser.home=' + str(self.root / 'home'),
                                      '-Djava.io.tmpdir=' + self.env['TMPDIR'], '--source', '21',
                                      str(helper), str(self.root / 'raw/screen.png')],
                                      'screen-helper', 10)
        screen.update(status)
        path = self.root / 'raw/screen.png'
        if status == {'exit_code': 0, 'timed_out': False}:
            png = read_regular(path, PNG_LIMIT)
            require(png[:8] == b'\x89PNG\r\n\x1a\n', '截图不是 PNG')
            require(self.server.alive(), '截图期间专用 Xvfb 退出')
            check_deadline(self.cutoff)
            write_new(self.root / 'evidence/startup-screen.png', png)
            check_deadline(self.cutoff)
            screen['status'] = 'CAPTURED'
        else:
            screen['status'] = 'UNAVAILABLE'
        self.evidence_text(child.err, 'screen-helper.stderr.log', 16384)
        windows = {'kind': 'window_titles', 'status': 'UNAVAILABLE_TOOL_MISSING'}
        self.summary['observations'].append(windows)
        if tools['xwininfo']:
            require(self.server.alive(), '专用 Xvfb 已退出')
            child, status = self.run_tool([tools['xwininfo'], '-root', '-tree'], 'window-titles', 3)
            windows.update(status)
            windows['status'] = 'CAPTURED' if status == {'exit_code': 0, 'timed_out': False} else 'UNAVAILABLE'
            self.evidence_text(child.out, 'window-titles.log', 32768)
        for index in range(3):
            entry = {'kind': 'thread_dump', 'index': index + 1, 'status': 'UNAVAILABLE',
                     'at_seconds': round(time.monotonic() - self.started, 2)}
            self.summary['observations'].append(entry)
            if not tools['jcmd']:
                entry['reason'] = '固定 JBR 未带 jcmd；不跨版本或改用强制 attach'
                break
            try:
                pid = checked_jvm(ide, idea, self.cutoff)
                child, status = self.run_tool([str(tools['jcmd']), '-J-Duser.home=' + str(self.root / 'home'),
                                              '-J-Djava.io.tmpdir=' + self.env['TMPDIR'], str(pid), 'Thread.print', '-l'],
                                             'thread-' + str(index + 1), 6)
                entry.update(status)
                # pidfd 与未回收直接子进程约束保证数字 PID 无法被复用；仍复核活跃身份。
                ide.handles[0].current()
                text = self.evidence_text(child.out, 'thread-' + str(index + 1) + '.log', DUMP_LIMIT)
                self.evidence_text(child.err, 'thread-' + str(index + 1) + '.stderr.log', 16384)
                entry['status'] = ('CAPTURED' if status == {'exit_code': 0, 'timed_out': False}
                                   and 'Full thread dump' in text else 'UNAVAILABLE')
                entry['pid'] = pid
                entry['start_ticks'] = ide.handles[0].identity['start']
                entry['toolchain'] = 'PINNED_IDEA_JBR_JCMD'
            except (OSError, ValueError) as exc:
                entry['reason'] = type(exc).__name__ + ': ' + str(exc)
                break
            if index < 2:
                until = min(self.cutoff, time.monotonic() + 1.5)
                while time.monotonic() < until:
                    self.tick()
                    time.sleep(.05)

    def cleanup(self):
        for child in reversed(self.children):
            try:
                self.summary['cleanup_errors'].extend(child.stop(self.cleanup_deadline))
            except (OSError, ValueError, subprocess.SubprocessError) as exc:
                self.summary['cleanup_errors'].append(type(exc).__name__)
        self.summary['registered_process_count'] = sum(len(child.handles) for child in self.children)
        self.summary['registered_processes_exit_verified'] = bool(self.children) and all(
            select.select([item.fd], [], [], 0)[0] for child in self.children for item in child.handles)
        for child in self.children:
            child.close()
        self.summary['elapsed_seconds_before_summary'] = round(time.monotonic() - self.started, 3)
        if self.summary['cleanup_errors']:
            self.summary['outcome'] = 'OWNERSHIP_UNVERIFIED'


def execute(args):
    started = time.monotonic()
    require(120 <= args.seconds <= MAX_SECONDS, '探针协作式时间目标只能在 120–180 秒之间')
    cutoff = started + args.seconds - RESERVE_SECONDS
    idea, plugins = absolute(args.idea_home), absolute(args.plugins_home)
    root = checked_root(args.run_root, os.environ['RUNNER_TEMP'], [idea, plugins, Path(__file__).resolve().parents[2]])
    new_directory(root)
    for name in ('raw', 'evidence', 'home', 'xdg-config', 'xdg-cache', 'xdg-data'):
        check_deadline(cutoff)
        new_directory(root / name)
    # 本候选只允许 fresh hosted CI；不主动读取个人 profile/凭据，不宣称阻止 JVM 的任意外部读。
    env = sanitized_environment()
    for key in ('DISPLAY', 'XAUTHORITY'):
        env.pop(key, None)
    probe = Probe(root, env, args.seconds, started=started)
    ide = None
    try:
        tools = preflight(idea, plugins, root, probe.summary['metadata_reads'])
        check_deadline(probe.cutoff)
        probe.summary['toolchain'] = {'idea_build': 'IU-' + tools['pins']['idea']['build'],
                                     'academy_version': tools['pins']['academy']['version']}
        probe.summary['runtime_tools'] = {key: bool(tools[key]) for key in ('xvfb', 'java', 'jcmd', 'xwininfo')}
        probe.summary['runtime_metadata'] = tools['runtime_metadata']
        probe.env = isolated_environment(idea, plugins, root)
        check_deadline(probe.cutoff)
        command = diagnostic_command(idea, root)
        probe.display(tools)
        # Xvfb 启动后再次确认 archive/target/report 均不存在，再启动唯一 validateCourse。
        command = diagnostic_command(idea, root)
        ide = probe.launch(command, 'idea')
        probe.summary['ide_pid'] = ide.proc.pid
        probe.summary['ide_start_ticks'] = ide.handles[0].identity['start']
        observed = False
        while ide.alive() and time.monotonic() < probe.cutoff:
            probe.tick()
            if not observed and time.monotonic() - probe.started >= 45:
                observed = True
                probe.observe(ide, idea, tools)
            time.sleep(.1)
        timed_out = ide.alive()
        # 先保留停止前日志，再发任何清理信号，避免 shutdown 噪声覆盖启动等待。
        texts = []
        log_deadline = min(probe.cleanup_deadline, time.monotonic() + 2)
        for source, name in ((ide.out, 'idea.stdout.log'), (ide.err, 'idea.stderr.log'),
                             (root / 'diagnostic-profile/log/idea.log', 'idea-pretermination.log')):
            try:
                texts.append(probe.evidence_text(source, name, LOG_LIMIT, log_deadline))
            except FileNotFoundError:
                pass
        if not timed_out:
            ide.proc.wait(timeout=0)
        missing = root / 'intentionally-missing-diagnostic-course.zip'
        probe.summary['ide_exit_code_before_cleanup'] = ide.proc.returncode
        probe.summary['timed_out'] = timed_out
        probe.summary['outcome'] = classify(ide.proc.returncode, timed_out, texts, missing,
                                            (root / 'never-an-acceptance-report.json').exists()
                                            or (root / 'never-an-acceptance-report.json').is_symlink(),
                                            missing.exists() or missing.is_symlink())
        probe.summary['observation_note'] = ('已到采集时间' if observed else 'IDE 提前退出，未保留仍在运行的等待现场')
    except TimeoutError as exc:
        probe.summary['outcome'] = 'UNRESOLVED_TIMEOUT'
        probe.summary['timed_out'] = True
        probe.summary['error'] = str(exc)
    except OwnershipError as exc:
        probe.summary['outcome'] = 'OWNERSHIP_UNVERIFIED'
        probe.summary['error'] = str(exc)
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError, zipfile.BadZipFile, ET.ParseError) as exc:
        # 不输出 traceback、环境变量或不受控目录；错误消息经既有脱敏器处理。
        probe.summary['error'] = sanitize_text(type(exc).__name__ + ': ' + str(exc))
    finally:
        # 包括采集辅助工具失败的路径也先保存本次 IDE 日志，再清理自有进程。
        if ide is not None:
            log_deadline = min(probe.cleanup_deadline, time.monotonic() + 2)
            for source, name in ((ide.out, 'idea.stdout.log'), (ide.err, 'idea.stderr.log'),
                                 (root / 'diagnostic-profile/log/idea.log', 'idea-pretermination.log')):
                if not (root / 'evidence' / name).exists():
                    try:
                        probe.evidence_text(source, name, LOG_LIMIT, log_deadline)
                    except (OSError, ValueError) as exc:
                        probe.summary.setdefault('unavailable_logs', []).append({'name': name, 'error': type(exc).__name__})
        probe.cleanup()
        check_deadline(probe.deadline)
        record(root / 'evidence/diagnostic-summary.json', probe.summary)
        check_deadline(probe.deadline)
    return OUTCOMES[probe.summary['outcome']]


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--idea-home', type=Path, required=True)
    parser.add_argument('--plugins-home', type=Path, required=True)
    parser.add_argument('--run-root', type=Path, required=True)
    parser.add_argument('--seconds', type=int, default=MAX_SECONDS)
    args = parser.parse_args()
    try:
        code = execute(args)
    except (OSError, ValueError) as exc:
        print(json.dumps({'outcome': 'PREFLIGHT_OR_COLLECTION_ERROR',
                          'error_type': type(exc).__name__, 'acceptance_pass': False}, ensure_ascii=False))
        code = 23
    raise SystemExit(code)
