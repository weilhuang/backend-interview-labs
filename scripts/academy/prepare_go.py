#!/usr/bin/env python3
"""Prepare the reviewed native Go runtime and module cache in a fresh CI root.

Only this setup step may use the network. It downloads one pinned official Go
archive and runs Go's download/verify commands over two authenticated module
metadata files, never course code, build scripts, installers, or global config.
Native validation consumes the exported runtime/cache with network disabled.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import selectors
import signal
import stat
import subprocess
import tarfile
import time
import urllib.request

from extract_toolchain import normalized, validate_members
from safe_io import (absolute, directory_fd, exclusive_writer, new_directory,
                     read_regular, regular_reader, validate_directory, write_new)

PINS = json.loads(read_regular(Path(__file__).absolute().with_name('go-toolchain.json'), 4096))
GO_VERSION = PINS['version']
GO_VERSION_OUTPUT = 'go version go' + GO_VERSION + ' ' + PINS['platform']
GO_ARCHIVE_NAME = 'go' + GO_VERSION + '.linux-amd64.tar.gz'
GO_ARCHIVE_URL = PINS['url']
GO_ARCHIVE_SHA256 = PINS['sha256']
GO_ARCHIVE_SIZE = PINS['size_bytes']
if (set(PINS) != {'version', 'url', 'sha256', 'size_bytes', 'platform'} or
        not re.fullmatch(r'[1-9][0-9]*\.[0-9]+\.[0-9]+', GO_VERSION) or
        PINS['platform'] != 'linux/amd64' or
        GO_ARCHIVE_URL != 'https://go.dev/dl/' + GO_ARCHIVE_NAME or
        not re.fullmatch('[0-9a-f]{64}', GO_ARCHIVE_SHA256) or
        type(GO_ARCHIVE_SIZE) is not int or not 0 < GO_ARCHIVE_SIZE <= 128 * 1024 * 1024):
    raise ValueError('invalid pinned Go toolchain metadata')
MODULE_PATHS = ('go-course/http/gin-pipeline/go/go.mod',
                'go-course/http/gin-pipeline/go/go.sum')
BOOTSTRAP_TIMEOUT = 270
DOWNLOAD_TIMEOUT = 90
MAX_UNPACKED_BYTES = 512 * 1024 * 1024
MAX_OUTPUT_BYTES = 1024 * 1024
MAX_CACHE_BYTES = 1024 * 1024 * 1024
MAX_CACHE_ENTRIES = 100000
PROOF_NAME = 'bootstrap.json'


def require(condition, message):
    if not condition:
        raise ValueError(message)


def remaining(deadline):
    value = deadline - time.monotonic()
    if value <= 0:
        raise TimeoutError('Go bootstrap time budget exceeded')
    return value


def file_sha256(path):
    with regular_reader(path) as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def expected_root(environment):
    temporary = environment.get('RUNNER_TEMP', '')
    require(temporary and Path(temporary).is_absolute(), 'absolute RUNNER_TEMP required')
    require(not any(c in temporary for c in '\r\n\0'), 'invalid RUNNER_TEMP')
    root = absolute(temporary)
    validate_directory(root)
    for key in ('GITHUB_RUN_ID', 'GITHUB_RUN_ATTEMPT'):
        require(re.fullmatch(r'[1-9][0-9]{0,19}', environment.get(key, '')),
                'invalid ' + key)
    return root / ('academy-go-' + environment['GITHUB_RUN_ID'] + '-' +
                   environment['GITHUB_RUN_ATTEMPT'])


def read_module_inputs(repo):
    """Use only sealed module metadata; never copy a Go source/workspace file."""
    validate_directory(repo)
    manifest_bytes = read_regular(repo / 'authoring/unified-course/manifest.json',
                                  8 * 1024 * 1024)
    manifest = json.loads(manifest_bytes)
    require(manifest.get('schema_version') == 1, 'unsupported sealed manifest')
    expected = manifest.get('expected_manifest', {})
    overlay = manifest.get('overlay_manifest', {})
    data = {}
    hashes = {}
    for relative in MODULE_PATHS:
        digest = expected.get(relative)
        require(isinstance(digest, str) and re.fullmatch('[0-9a-f]{64}', digest),
                'sealed module input missing: ' + relative)
        require(overlay.get(relative) == digest, 'sealed overlay module input mismatch: ' + relative)
        content = read_regular(repo / 'authoring/unified-course/overlay' / relative,
                               256 * 1024)
        require(hashlib.sha256(content).hexdigest() == digest,
                'sealed module input mismatch: ' + relative)
        data[relative] = content
        hashes[relative] = digest
    require(re.search(rb'^go ' + re.escape(GO_VERSION.encode()) + rb'\s*$', data[MODULE_PATHS[0]], re.MULTILINE),
            'sealed module Go version differs from pinned runtime')
    return data, hashes, hashlib.sha256(manifest_bytes).hexdigest()


class OfficialRedirect(urllib.request.HTTPRedirectHandler):
    """The fixed go.dev URL may redirect only to its official binary URL."""
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        require(request.full_url == GO_ARCHIVE_URL and
                newurl == 'https://dl.google.com/go/' + GO_ARCHIVE_NAME,
                'unexpected Go download redirect')
        return super().redirect_request(request, fp, code, msg, headers, newurl)


def download_archive(destination, deadline):
    deadline = min(deadline, time.monotonic() + DOWNLOAD_TIMEOUT)
    # No inherited proxy credentials, authentication handlers, or cookies.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}),
                                        OfficialRedirect())
    request = urllib.request.Request(GO_ARCHIVE_URL,
                                     headers={'User-Agent': 'academy-pinned-go-bootstrap/1'})
    digest = hashlib.sha256()
    size = 0
    with exclusive_writer(destination) as output:
        with opener.open(request, timeout=min(15, remaining(deadline))) as response:
            require(response.status == 200, 'Go archive HTTP status is not 200')
            length = response.headers.get('Content-Length')
            require(length is None or length == str(GO_ARCHIVE_SIZE),
                    'Go archive Content-Length differs from pin')
            while True:
                remaining(deadline)
                chunk = response.read(min(1024 * 1024, GO_ARCHIVE_SIZE - size + 1))
                if not chunk:
                    break
                size += len(chunk)
                require(size <= GO_ARCHIVE_SIZE, 'Go archive exceeds pinned size')
                digest.update(chunk)
                output.write(chunk)
    require(size == GO_ARCHIVE_SIZE, 'Go archive size differs from pin')
    require(digest.hexdigest() == GO_ARCHIVE_SHA256, 'Go archive SHA256 mismatch')


def extract_go_archive(source, destination, deadline):
    """Reuse reviewed archive validators, with Go's stricter no-link policy."""
    validate_directory(destination)
    require(not any(destination.iterdir()), 'Go output is not empty')
    with regular_reader(source) as stream, tarfile.open(fileobj=stream, mode='r:gz') as archive:
        members = []
        rows = []
        for member in archive:
            remaining(deadline)
            require(len(members) < 20000, 'Go archive entry count exceeds bound')
            name = normalized(member.name)
            require(member.isdir() or member.isfile(), 'Go archive link/special member rejected')
            require(not member.issparse(), 'Go archive sparse member rejected')
            require(member.size >= 0, 'Go archive negative member size')
            require(not member.isdir() or member.size == 0, 'Go archive directory contains payload')
            kind = 'dir' if member.isdir() else 'file'
            require(name != 'go' or kind == 'dir', 'Go archive root must be a directory')
            members.append(member)
            rows.append((name, kind, member.size, ''))
        validate_members(rows, 'go', MAX_UNPACKED_BYTES)
        for member, (name, kind, size, _) in zip(members, rows):
            remaining(deadline)
            parts = name.split('/')[1:]
            if not parts:
                continue
            target = destination.joinpath(*parts)
            if kind == 'dir':
                target.mkdir(mode=0o700, parents=True, exist_ok=True)
                validate_directory(target)
            else:
                target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                validate_directory(target.parent)
                with archive.extractfile(member) as data, exclusive_writer(target) as output:
                    copied = 0
                    while True:
                        remaining(deadline)
                        chunk = data.read(1024 * 1024)
                        if not chunk:
                            break
                        copied += len(chunk)
                        require(copied <= size, 'Go archive member exceeds declared size')
                        output.write(chunk)
                require(copied == size, 'Go archive member size mismatch')
                # Preserve executability, never ownership, setuid, or world writes.
                with directory_fd(target.parent) as parent:
                    os.chmod(target.name, 0o700 if member.mode & 0o111 else 0o600,
                             dir_fd=parent, follow_symlinks=False)
    executable = destination / 'bin/go'
    with regular_reader(executable) as stream:
        require(bool(os.fstat(stream.fileno()).st_mode & stat.S_IXUSR),
                'pinned Go executable is not executable')


def isolated_environment(root):
    """An explicit allowlist: no token, shell hook, toolchain, proxy, or user config."""
    return {
        'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8', 'LC_ALL': 'C.UTF-8',
        'HOME': str(root / 'home'), 'TMPDIR': str(root / 'tmp'),
        'GOROOT': str(root / 'go'), 'GOPATH': str(root / 'gopath'),
        'GOCACHE': str(root / 'build-cache'), 'GOMODCACHE': str(root / 'module-cache'),
        'GOTOOLCHAIN': 'local', 'GOENV': 'off', 'GOWORK': 'off',
        'GOPROXY': 'https://proxy.golang.org', 'GOSUMDB': 'sum.golang.org',
        'GOPRIVATE': '', 'GONOPROXY': '', 'GONOSUMDB': '',
        'GOFLAGS': '-mod=readonly', 'GOVCS': '*:off', 'GOAUTH': 'off',
        'GOTELEMETRY': 'off', 'CGO_ENABLED': '0', 'GOOS': 'linux', 'GOARCH': 'amd64',
    }


def run_checked(argv, cwd, environment, timeout):
    """Bound command runtime and captured output; kill its process group on failure."""
    started = time.monotonic()
    output = {'stdout': bytearray(), 'stderr': bytearray()}
    process = subprocess.Popen(argv, cwd=str(cwd), env=environment,
                               stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, start_new_session=True)
    try:
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout, selectors.EVENT_READ, 'stdout')
            selector.register(process.stderr, selectors.EVENT_READ, 'stderr')
            while selector.get_map():
                left = remaining(started + timeout)
                for key, _ in selector.select(min(left, 0.25)):
                    chunk = os.read(key.fileobj.fileno(), 65536)
                    if not chunk:
                        selector.unregister(key.fileobj)
                        continue
                    output[key.data].extend(chunk)
                    require(sum(map(len, output.values())) <= MAX_OUTPUT_BYTES,
                            'Go command output exceeds bound')
            status = process.wait(timeout=remaining(started + timeout))
        require(status == 0, 'Go ' + ' '.join(argv[1:]) + ' failed with exit ' + str(status) +
                ': ' + bytes(output['stderr'] + output['stdout']).decode('utf-8', errors='replace')[:2048])
    except BaseException:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait(timeout=5)
        raise
    finally:
        process.stdout.close()
        process.stderr.close()
    return {key: bytes(value) for key, value in output.items()}


def cache_inventory(cache, deadline):
    """Require a bounded, regular-file-only private cache before handing it off."""
    count = size = 0
    pending = [cache]
    while pending:
        remaining(deadline)
        directory = pending.pop()
        validate_directory(directory)
        for path in directory.iterdir():
            count += 1
            require(count <= MAX_CACHE_ENTRIES, 'Go module cache entry bound exceeded')
            info = path.lstat()
            if stat.S_ISDIR(info.st_mode):
                pending.append(path)
            else:
                require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1,
                        'Go module cache link/special entry rejected')
                size += info.st_size
                require(size <= MAX_CACHE_BYTES, 'Go module cache size bound exceeded')
    require(count > 0 and size > 0, 'Go module cache is empty')
    return {'entries': count, 'bytes': size}


def append_github_env(path, root):
    """Append only the two single-line verified outputs, with no-follow checks."""
    values = ('GO_EXECUTABLE=' + str(root / 'go/bin/go') + '\n' +
              'GO_MODULE_CACHE=' + str(root / 'module-cache') + '\n').encode()
    with directory_fd(path.parent) as parent:
        fd = os.open(path.name, os.O_WRONLY | os.O_APPEND | os.O_NOFOLLOW |
                     os.O_NONBLOCK, dir_fd=parent)
        try:
            info = os.fstat(fd)
            require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1,
                    'GITHUB_ENV must be a nonlinked regular file')
            require(os.write(fd, values) == len(values), 'short GITHUB_ENV write')
        finally:
            os.close(fd)


def prepare(repo, output, github_env, report, environment=None):
    environment = dict(os.environ if environment is None else environment)
    started = time.monotonic()
    deadline = started + BOOTSTRAP_TIMEOUT
    require(platform.system() == 'Linux' and platform.machine() == 'x86_64',
            'pinned Go runtime requires Linux amd64')
    repo, output, github_env, report = map(absolute, (repo, output, github_env, report))
    require(str(repo) == environment.get('GITHUB_WORKSPACE'), 'repository differs from GITHUB_WORKSPACE')
    require(output == expected_root(environment), 'Go output is not the exact run-scoped root')
    require(not output.is_relative_to(repo) and not repo.is_relative_to(output),
            'Go output must be outside the repository')
    require(not report.is_relative_to(repo) and report != github_env and
            report.is_relative_to(output.parent),
            'report must be separate, outside the repository, and under RUNNER_TEMP')
    require(str(github_env) == environment.get('GITHUB_ENV'), 'GITHUB_ENV destination mismatch')
    require(not github_env.is_relative_to(repo) and not github_env.is_relative_to(output),
            'GITHUB_ENV must be outside repository/runtime')
    validate_directory(report.parent)
    # Fail before a download or execution if a report/env target is unsafe.
    require(not os.path.lexists(report), 'Go report already exists')
    with regular_reader(github_env) as stream:
        require(os.fstat(stream.fileno()).st_nlink == 1, 'GITHUB_ENV hardlink rejected')
    inputs, hashes, manifest_hash = read_module_inputs(repo)
    new_directory(output)  # Deliberately refuses even an empty preexisting root.
    for name in ('go', 'home', 'tmp', 'gopath', 'build-cache', 'module-cache', 'module-inputs'):
        new_directory(output / name)
    module = output / 'module-inputs'
    for relative, data in inputs.items():
        write_new(module / Path(relative).name, data)
    archive = output / GO_ARCHIVE_NAME
    download_archive(archive, deadline)
    extract_go_archive(archive, output / 'go', deadline)
    executable = output / 'go/bin/go'
    executable_hash = file_sha256(executable)
    child_env = isolated_environment(output)
    commands = []
    version_output = None
    for args, budget in ((['version'], 10), (['mod', 'download'], 110), (['mod', 'verify'], 25)):
        command = [str(executable), *args]
        result = run_checked(command, module, child_env, min(budget, remaining(deadline)))
        if args == ['version']:
            version_output = result['stdout'].decode('utf-8').strip()
            require(version_output == GO_VERSION_OUTPUT and not result['stderr'],
                    'downloaded Go version identity mismatch')
        if args == ['mod', 'verify']:
            require(result['stdout'].strip() == b'all modules verified' and not result['stderr'],
                    'Go module verification did not confirm all modules')
        for relative, data in inputs.items():
            require(read_regular(module / Path(relative).name, 256 * 1024) == data,
                    'Go command changed sealed module input: ' + relative)
        commands.append({'argv': command, 'timeout_seconds': budget, 'exit_code': 0,
                         'stdout_sha256': hashlib.sha256(result['stdout']).hexdigest(),
                         'stderr_sha256': hashlib.sha256(result['stderr']).hexdigest()})
    require(file_sha256(executable) == executable_hash, 'Go executable changed during preparation')
    inventory = cache_inventory(output / 'module-cache', deadline)
    # Re-read source pins: successful setup must not conceal a changed checkout.
    _, current_hashes, current_manifest_hash = read_module_inputs(repo)
    require(current_hashes == hashes and current_manifest_hash == manifest_hash,
            'sealed module inputs changed during preparation')
    proof = {'schema_version': 1, 'status': 'prepared', 'version': GO_VERSION,
             'compiler_identity': version_output, 'version_output': version_output, 'run_id': environment['GITHUB_RUN_ID'],
             'run_attempt': environment['GITHUB_RUN_ATTEMPT'],
             'executable': str(executable), 'executable_sha256': executable_hash,
             'module_cache': str(output / 'module-cache'), 'module_cache_inventory': inventory,
             'archive': {'url': GO_ARCHIVE_URL, 'sha256': GO_ARCHIVE_SHA256,
                         'size_bytes': GO_ARCHIVE_SIZE},
             'module_inputs': hashes, 'sealed_manifest_sha256': manifest_hash,
             'commands': commands, 'seconds': round(time.monotonic() - started, 3)}
    payload = (json.dumps(proof, indent=2, sort_keys=True) + '\n').encode()
    write_new(output / PROOF_NAME, payload)
    write_new(report, payload)
    remaining(deadline)
    append_github_env(github_env, output)
    return proof


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('repo', 'output', 'github-env', 'report'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    # A final wall-clock guard also bounds DNS, archive parsing, and filesystem IO.
    # Each child command separately kills its process group when interrupted.
    def timed_out(signum, frame):
        raise TimeoutError('Go bootstrap exceeded the 270-second wall-clock limit')
    previous = signal.signal(signal.SIGALRM, timed_out)
    signal.setitimer(signal.ITIMER_REAL, BOOTSTRAP_TIMEOUT)
    try:
        prepare(args.repo, args.output, args.github_env, args.report)
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)


if __name__ == '__main__':
    main()
