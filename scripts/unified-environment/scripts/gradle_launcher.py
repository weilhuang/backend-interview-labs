#!/usr/bin/env python3
"""固定Gradle发行启动器；准备仅标准库，不运行Java，不重新封装Wrapper。"""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import urllib.request
import urllib.parse
import zipfile

ROOT = Path(__file__).resolve().parents[1]
OFFICIAL_URL = 'https://services.gradle.org/distributions/gradle-8.10.2-bin.zip'
VERSION = '8.10.2'
MAX_DOWNLOAD = 256 * 1024**2
MAX_EXPANDED = 1024**3


class LauncherError(Exception):
    pass


def distribution():
    path = ROOT / 'gradle/wrapper/gradle-wrapper.properties'
    props = {}
    for line in path.read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, value = line.split('=', 1)
        if key in props:
            raise LauncherError('Gradle发行属性存在重复键')
        props[key] = value.replace('\\:', ':')
    if props.get('distributionUrl') != OFFICIAL_URL:
        raise LauncherError('仅支持已审定的官方Gradle8.10.2发行URL，不接受浮动版本或其他来源')
    digest = props.get('distributionSha256Sum', '')
    if not re.fullmatch(r'[a-f0-9]{64}', digest):
        raise LauncherError('gradle-wrapper.properties缺少固定发行SHA256')
    return {'version': VERSION, 'url': OFFICIAL_URL, 'sha256': digest}


def sha256(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024*1024), b''):
            digest.update(block)
    return digest.hexdigest()


def cache_root():
    explicit = os.environ.get('LAB_GRADLE_CACHE')
    if explicit:
        path = Path(explicit).expanduser()
        if not path.is_absolute():
            raise LauncherError('LAB_GRADLE_CACHE必须为课程树外的绝对路径')
    else:
        base = os.environ.get('XDG_CACHE_HOME')
        if base:
            path = Path(base).expanduser() / 'totalacademy/gradle'
            if not path.is_absolute():
                raise LauncherError('XDG_CACHE_HOME必须为绝对路径')
        else:
            path = Path.home() / (('Library/Caches' if sys.platform == 'darwin' else '.cache')) / 'totalacademy/gradle'
    path = path.resolve()
    root = ROOT.resolve()
    if path == root or root in path.parents:
        raise LauncherError('Gradle可信缓存必须放在课程树外；不把运行时塞入Academy课程')
    return path


def key_for(spec):
    return 'gradle-' + spec['version'] + '-' + spec['sha256'][:16]


def archive_entries(archive, spec):
    result = {}
    total = 0
    prefix = 'gradle-' + spec['version']
    for entry in archive.infolist():
        name = entry.filename
        clean = name[:-1] if name.endswith('/') else name
        parts = clean.split('/')
        kind = stat.S_IFMT(entry.external_attr >> 16)
        if (not clean or '\\' in name or ':' in name or any(part in ('', '.', '..') for part in parts)
                or parts[0] != prefix or name.startswith('/') or re.search(r'[\x00-\x1f\x7f]', name)
                or stat.S_ISLNK(entry.external_attr >> 16) or kind not in (0, stat.S_IFDIR, stat.S_IFREG)
                or entry.flag_bits & 1):
            raise LauncherError('Gradle ZIP含不安全路径、符号链接、特殊文件或加密成员；拒绝解压')
        if clean in result:
            raise LauncherError('Gradle ZIP包含重复目录/文件路径')
        total += entry.file_size
        result[clean] = entry
    if len(result) > 10000 or total > MAX_EXPANDED:
        raise LauncherError('Gradle发行ZIP超出允许的条目或展开大小边界')
    if prefix + '/bin/gradle' not in result:
        raise LauncherError('Gradle ZIP缺少固定发行启动文件')
    return result, total


def receipt_path(base, spec):
    return base / (key_for(spec) + '.ready.json')


def verify_managed(base, spec):
    receipt = receipt_path(base, spec)
    if not receipt.is_file() or receipt.is_symlink():
        raise LauncherError('缺少可信Gradle运行时；先显式执行 prepare --zip 文件 或 prepare --download')
    data = json.loads(receipt.read_text(encoding='utf-8'))
    name = data.get('directory', '')
    if (data.get('schema_version') != 1 or data.get('distribution') != spec
            or not isinstance(name, str) or not re.fullmatch(re.escape(key_for(spec)) + r'-payload-[A-Za-z0-9_-]+', name)):
        raise LauncherError('Gradle完整性凭证无效；不覆盖或删除现有缓存，请另选全新缓存目录')
    payload = base / name
    if not payload.is_dir() or payload.is_symlink() or payload.resolve().parent != base.resolve():
        raise LauncherError('Gradle缓存目录缺失或经符号链接逃逸')
    archive_path = payload / 'distribution.zip'
    if archive_path.is_symlink() or not archive_path.is_file() or sha256(archive_path) != spec['sha256']:
        raise LauncherError('Gradle缓存ZIP的SHA256不匹配；拒绝执行，不自动删除或覆盖')
    observed = {}
    with zipfile.ZipFile(archive_path) as archive:
        entries, _ = archive_entries(archive, spec)
        for name, entry in entries.items():
            target = payload.joinpath(*PurePosixPath(name).parts)
            if target.is_symlink() or payload.resolve() not in target.resolve().parents:
                raise LauncherError('Gradle缓存包含不安全链接')
            if entry.is_dir():
                if not target.is_dir(): raise LauncherError('Gradle缓存目录不完整')
                continue
            digest = hashlib.sha256()
            with archive.open(entry) as source:
                for block in iter(lambda: source.read(1024*1024), b''): digest.update(block)
            observed[name] = digest.hexdigest()
            if not target.is_file() or sha256(target) != observed[name]:
                raise LauncherError('Gradle缓存内容与已校验ZIP不一致；拒绝执行')
        allowed = set(entries) | {'distribution.zip', 'receipt.json'}
        for name in entries:
            allowed.update(parent.as_posix() for parent in PurePosixPath(name).parents if parent.as_posix() != '.')
        for target in payload.rglob('*'):
            if target.is_symlink() or target.relative_to(payload).as_posix() not in allowed:
                raise LauncherError('Gradle缓存出现未登记文件或链接；拒绝执行')
    if data.get('files') != observed or (payload/'receipt.json').read_text(encoding='utf-8') != receipt.read_text(encoding='utf-8'):
        raise LauncherError('Gradle完整性凭证与已校验ZIP不一致')
    binary = payload / ('gradle-' + spec['version']) / 'bin/gradle'
    if not os.access(binary, os.X_OK):
        raise LauncherError('Gradle缓存启动文件不可执行；不自动修改已有缓存权限')
    return binary


class OfficialRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        parsed = urllib.parse.urlsplit(newurl)
        allowed = {'services.gradle.org', 'downloads.gradle.org', 'github.com', 'objects.githubusercontent.com', 'release-assets.githubusercontent.com'}
        if parsed.scheme != 'https' or parsed.hostname not in allowed or parsed.username or parsed.password:
            raise LauncherError('官方Gradle下载重定向到未允许位置；停止下载，不换第三方镜像')
        return super().redirect_request(request, fp, code, msg, headers, newurl)


def download_archive(spec, destination):
    opener = urllib.request.build_opener(OfficialRedirect())
    request = urllib.request.Request(spec['url'], headers={'User-Agent': 'totalAcademy-fixed-gradle-launcher/1'})
    count = 0
    with opener.open(request, timeout=30) as source, destination.open('xb') as target:
        while True:
            block = source.read(1024*1024)
            if not block: break
            count += len(block)
            if count > MAX_DOWNLOAD: raise LauncherError('下载超过允许大小；停止，不发布运行时')
            target.write(block)


def prepare(spec, zip_path=None, download=False):
    base = cache_root(); base.mkdir(mode=0o700, parents=True, exist_ok=True)
    ready = receipt_path(base, spec)
    if ready.exists() or ready.is_symlink():
        verify_managed(base, spec)
        print('现有可信Gradle缓存已完整校验；没有覆盖文件')
        return 0
    lock = base / (key_for(spec) + '.prepare-lock')
    try: lock.mkdir(mode=0o700)
    except FileExistsError: raise LauncherError('准备锁已存在；可能另一个准备正在运行。不删除未知锁/目录，请检查或换全新缓存位置') from None
    payload = None
    published = False
    try:
        payload = Path(tempfile.mkdtemp(prefix=key_for(spec)+'-payload-', dir=base))
        archive_path = payload / 'distribution.zip'
        if download:
            print('显式下载官方固定Gradle发行；仅SHA256一致后才解压和发布')
            download_archive(spec, archive_path)
        else:
            source = Path(zip_path).expanduser()
            if not source.is_file() or source.stat().st_size > MAX_DOWNLOAD:
                raise LauncherError('已有Gradle ZIP不存在或超出允许大小')
            with source.open('rb') as incoming, archive_path.open('xb') as out: shutil.copyfileobj(incoming, out, 1024*1024)
        if sha256(archive_path) != spec['sha256']:
            raise LauncherError('Gradle发行SHA256不匹配；拒绝解压，不发布缓存')
        file_digests = {}
        with zipfile.ZipFile(archive_path) as archive:
            entries, total = archive_entries(archive, spec)
            if shutil.disk_usage(base).free < total + 64*1024**2:
                raise LauncherError('缓存所在磁盘不足以展开发行并保留安全余量；不清理已有数据')
            for name, entry in entries.items():
                target = payload.joinpath(*PurePosixPath(name).parts)
                if entry.is_dir(): target.mkdir(parents=True, exist_ok=True); continue
                target.parent.mkdir(parents=True, exist_ok=True)
                digest = hashlib.sha256()
                with archive.open(entry) as incoming, target.open('xb') as out:
                    for block in iter(lambda: incoming.read(1024*1024), b''): out.write(block); digest.update(block)
                executable = bool((entry.external_attr >> 16) & 0o111) or name.endswith('/bin/gradle')
                target.chmod(0o755 if executable else 0o644)
                file_digests[name] = digest.hexdigest()
        receipt = {'schema_version': 1, 'distribution': spec, 'directory': payload.name, 'files': file_digests}
        raw = json.dumps(receipt, ensure_ascii=False, sort_keys=True, indent=2)+'\n'
        with (payload/'receipt.json').open('x', encoding='utf-8') as stream:
            stream.write(raw); stream.flush(); os.fsync(stream.fileno())
        # hard-link以独占方式原子发布凭证；已有文件/目录/链接都不会被替换。
        os.link(payload/'receipt.json', ready)
        published = True
        verify_managed(base, spec)
        print('Gradle可信运行时已准备并完整校验；位于课程树外，不含新Wrapper JAR')
        return 0
    finally:
        # 仅清理本次独占创建且尚未发布的临时目录，不触碰已有非托管目录。
        if payload is not None and not published: shutil.rmtree(payload)
        lock.rmdir()


def explicit_binary():
    value = os.environ.get('LAB_GRADLE_BIN')
    if not value: return None
    path = Path(value).expanduser()
    if not path.is_absolute() or not path.is_file() or not os.access(path, os.X_OK):
        raise LauncherError('LAB_GRADLE_BIN必须明确指向可信、绝对路径的可执行Gradle文件；不搜索PATH')
    result = subprocess.run([str(path), '--version'], text=True, capture_output=True, timeout=60, cwd=ROOT)
    if result.returncode or not re.search(r'^Gradle 8\.10\.2\s*$', result.stdout, re.MULTILINE):
        raise LauncherError('LAB_GRADLE_BIN版本不是固定Gradle8.10.2，拒绝运行')
    print('使用显式LAB_GRADLE_BIN：版本检查≠来源认证；该文件来源须由你独立信任', file=sys.stderr)
    return path


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    if sys.version_info < (3, 9): raise LauncherError('需要Python3.9+')
    if not args or args == ['launcher-help']:
        print('用法：bash scripts/gradle.sh <Gradle参数>；prepare --zip 已有ZIP；prepare --download；verify。普通执行不下载Gradle。')
        return 0
    spec = distribution()
    if args[0] == 'prepare':
        p = argparse.ArgumentParser(description='显式准备固定Gradle；不运行Java')
        group = p.add_mutually_exclusive_group(required=True)
        group.add_argument('--zip'); group.add_argument('--download', action='store_true')
        chosen = p.parse_args(args[1:]); return prepare(spec, chosen.zip, chosen.download)
    if args == ['verify']:
        verify_managed(cache_root(), spec); print('托管Gradle缓存及来源ZIP完整性通过；没有运行Java'); return 0
    binary = explicit_binary() or verify_managed(cache_root(), spec)
    return subprocess.run([str(binary)] + args, cwd=ROOT).returncode


if __name__ == '__main__':
    try: sys.exit(main())
    except (LauncherError, OSError, ValueError, KeyError, zipfile.BadZipFile, subprocess.TimeoutExpired) as exc:
        print('Gradle启动器错误：'+str(exc), file=sys.stderr); sys.exit(2)
    except KeyboardInterrupt: sys.exit(130)
