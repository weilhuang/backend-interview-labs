"""Read-only, fail-closed checks for the pinned IDEA vendor AppArmor action.

Candidates are PRIVATE JSON records, never public reports. Only public_evidence()
may leave the runner. The caller owns PID/pidfd/starttime checks around every call;
this module neither discovers processes nor installs, loads, or removes policy.
Filesystem overrides exist for synthetic fixtures, not runtime configuration.
"""
from contextlib import contextmanager
from contextvars import ContextVar
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import struct
import subprocess
import time
import secrets
import xml.etree.ElementTree as ET
import zipfile


TEXT_LIMIT = 64 * 1024
TOTAL_LIMIT = 256 * 1024
FILE_LIMIT = 8
CANDIDATE_LIMIT = 1001
OBSERVATION_SECONDS = 5
INVENTORY = Path('/sys/kernel/security/apparmor/profiles')
PROFILE_DIR = Path('/etc/apparmor.d')
CONFIG = Path('/etc/apparmor/parser.conf')
GENERATOR_JAR = 'lib/intellij.platform.ide.impl.jar'
GENERATOR_CLASS = 'com/intellij/ui/jcef/JBCefAppArmorUtils.class'
CORE_JAR = 'lib/intellij.platform.core.jar'
NAMES_CLASS = 'com/intellij/openapi/application/ApplicationNamesInfo.class'
PINNED = {
    GENERATOR_JAR: (73879154, '821d2a32ba787c838da451bcb9c4dbd8e7d9597522cc1a17f38093fdb5c1adf8'),
    CORE_JAR: (5250654, 'a2e9f5ab30b85f70b40c1f5d8cdcb98be3d67a44b4c389ece9da121d183c3581'),
    'bin/idea': (954448, '1767a903501b763698f7720edc4ebb3fba0c4ff8f418080b8cc51ab390cfaf37'),
    'jbr/bin/java': (23456, 'c1e804dff06d030b35e6d0fb3256a4bb744b31fb6db27fc36be06eb6a4780b5c'),
}
CLASS_HASHES = {
    GENERATOR_CLASS: '8348ea83c1e7021dec6b60df61e47de1a6390b5dfa3b3c9efac663db182d7ae0',
    NAMES_CLASS: 'de1b37eb6c796046ece82a3aa89267fa2db8a983fdcbd065998ba9a7550d8c87',
}
# This is deliberately a closed list. New dependencies require source review;
# even known files collectively remain subject to the eight-file budget.
INCLUDES = frozenset(('abi/4.0', 'tunables/global', 'local/chrome',
                      'tunables/home', 'tunables/multiarch', 'tunables/proc',
                      'tunables/alias', 'tunables/kernelvars', 'tunables/share'))
MODES = frozenset(('enforce', 'complain', 'kill', 'unconfined', 'prompt'))
CODES = frozenset(('PATH_UNSAFE', 'FILE_UNKNOWN', 'FILE_CHANGED', 'BOUNDS_EXCEEDED',
                   'VENDOR_MISMATCH', 'EXECUTABLE_MISMATCH', 'PRODUCT_UNKNOWN',
                   'PARSER_CONTEXT_UNKNOWN', 'INCLUDE_UNKNOWN', 'INVENTORY_UNKNOWN',
                   'PROFILE_COLLISION', 'DESTINATION_CHANGED', 'INSTALLED_MISMATCH',
                   'LOADED_MISMATCH', 'CONTEXT_UNKNOWN', 'CONTEXT_MISMATCH',
                   'CANDIDATE_INVALID'))
STEPS = frozenset(('UNSPECIFIED', 'CANDIDATE', 'VENDOR_METADATA', 'DESTINATION',
                   'KERNEL_INVENTORY', 'PROVIDER_ROUTE', 'PACKAGE_IDENTITY',
                   'PARSER_CONFIG', 'PARSER_VERSION', 'CACHE_LOCATION',
                   'INCLUDE_CLOSURE', 'PROVIDER_FRESHNESS', 'INSTALLED_BYTES',
                   'ACTIVE_CONTEXT'))
_CURRENT_STEP = ContextVar('apparmor_observation_step', default='UNSPECIFIED')


class ProfileError(ValueError):
    """Safe public exception: never contains paths, raw output, or OS messages."""
    def __init__(self, code, *, step='UNSPECIFIED'):
        self.code = code if type(code) is str and code in CODES else 'FILE_UNKNOWN'
        self.step = step if type(step) is str and step in STEPS else 'UNSPECIFIED'
        super().__init__(self.code)


def _fail(code, *, step=None):
    raise ProfileError(code, step=_CURRENT_STEP.get() if step is None else step) from None


@contextmanager
def _step(step, unknown_code='FILE_UNKNOWN'):
    """Attach a fixed observation role, preserving the innermost safe failure."""
    token = _CURRENT_STEP.set(step if type(step) is str and step in STEPS else 'UNSPECIFIED')
    try:
        yield
    except ProfileError as error:
        if error.step == 'UNSPECIFIED':
            error.step = _CURRENT_STEP.get()
        raise
    except (OSError, ValueError, TypeError, KeyError, IndexError, AttributeError,
            struct.error, zipfile.BadZipFile, ET.ParseError):
        _fail(unknown_code)
    finally:
        _CURRENT_STEP.reset(token)


def _sha(value):
    return hashlib.sha256(value).hexdigest()


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode()


def _path(value):
    p = Path(value)
    if not p.is_absolute() or '..' in p.parts or str(p) != str(value):
        _fail('PATH_UNSAFE')
    return p


def _exact_executable(value):
    p = _path(value)
    # Reject AppArmor glob/variable/namespace and shell syntax, including spaces.
    if len(str(p).encode()) > 4096 or not re.fullmatch(r'/[A-Za-z0-9_./-]+', str(p)):
        _fail('EXECUTABLE_MISMATCH')
    return p


def _trust(info, directory=False):
    if (not (stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode))
            or info.st_uid != 0 or info.st_mode & 0o022):
        _fail('PATH_UNSAFE')


def _trust_distro_alias(info):
    # Symlink permission bits do not protect their target on Linux. The link
    # itself must be root-owned, and its parent '/' is separately root-trusted.
    if not stat.S_ISLNK(info.st_mode) or info.st_uid != 0:
        _fail('PATH_UNSAFE')


def _identity(info):
    return [info.st_dev, info.st_ino, info.st_uid, info.st_mode,
            info.st_size, info.st_mtime_ns, info.st_ctime_ns]


class _Observation:
    def __init__(self, root=Path('/')):
        self.root = _path(root)
        self.deadline = time.monotonic() + OBSERVATION_SECONDS
        self.texts = {}

    def tick(self):
        if time.monotonic() >= self.deadline:
            _fail('BOUNDS_EXCEEDED')

    @contextmanager
    def directory(self, path, trusted=True):
        """Open every ancestor without following links, including the root."""
        self.tick()
        path = _path(path)
        fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            # Fixture roots are reached no-follow; their OS trust is simulated
            # at and below that boundary. Production's boundary is real '/'.
            for part in self.root.parts[1:]:
                nxt = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                os.close(fd)
                fd = nxt
            if trusted:
                self.directory_trust(os.fstat(fd), trusted)
            for part in path.parts[1:]:
                self.tick()
                nxt = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                os.close(fd)
                fd = nxt
                if trusted:
                    self.directory_trust(os.fstat(fd), trusted)
            yield fd
        finally:
            os.close(fd)

    @staticmethod
    def directory_trust(info, trusted):
        if trusted == 'search':
            # Absent provider probes may cross this runner's toolcache/home.
            # A selected OS executable still requires root-owned ancestors.
            if (not stat.S_ISDIR(info.st_mode) or info.st_uid not in (0, os.getuid())
                    or info.st_mode & 0o022):
                _fail('PATH_UNSAFE')
        else:
            _trust(info, directory=True)

    def entry(self, path, trusted=True):
        path = _path(path)
        try:
            with self.directory(path.parent, trusted) as directory:
                value = os.stat(path.name, dir_fd=directory, follow_symlinks=False)
                self.tick()
                if stat.S_ISLNK(value.st_mode):
                    _fail('PATH_UNSAFE')
                return value
        except FileNotFoundError:
            # Existing prefixes have still been checked no-follow; a missing
            # component is absence, unlike EACCES/ELOOP/ENOTDIR.
            return None

    @contextmanager
    def opened(self, path, trusted=True):
        path = _path(path)
        with self.directory(path.parent, trusted) as directory:
            fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
            try:
                info = os.fstat(fd)
                if not stat.S_ISREG(info.st_mode):
                    _fail('PATH_UNSAFE')
                if trusted:
                    _trust(info)
                yield fd, info
                self.tick()
                if _identity(os.fstat(fd)) != _identity(info):
                    _fail('FILE_CHANGED')
            finally:
                os.close(fd)

    def read(self, path, *, trusted=True, limit=TEXT_LIMIT, effective=False):
        with self.opened(path, trusted) as (fd, info):
            if info.st_size > limit:
                _fail('BOUNDS_EXCEEDED')
            data = bytearray()
            while len(data) <= limit:
                self.tick()
                block = os.read(fd, min(8192, limit + 1 - len(data)))
                if not block:
                    break
                data.extend(block)
            if len(data) > limit:
                _fail('BOUNDS_EXCEEDED')
            value = bytes(data)
            if effective:
                self.texts[str(path)] = len(value)
                if len(self.texts) > FILE_LIMIT or sum(self.texts.values()) > TOTAL_LIMIT:
                    _fail('BOUNDS_EXCEEDED')
            return value, {'path': str(path), 'identity': _identity(info), 'sha256': _sha(value)}

    def binary(self, path, expected=None, limit=16 * 1024 * 1024):
        with self.opened(path, trusted=expected is None) as (fd, info):
            maximum = expected[0] if expected else limit
            if info.st_size > maximum or (expected and info.st_size != maximum):
                _fail('VENDOR_MISMATCH' if expected else 'BOUNDS_EXCEEDED')
            h = hashlib.sha256()
            count = 0
            while True:
                self.tick()
                block = os.read(fd, min(1024 * 1024, maximum + 1 - count))
                if not block:
                    break
                count += len(block)
                if count > maximum:
                    _fail('BOUNDS_EXCEEDED')
                h.update(block)
            if expected and (count != expected[0] or h.hexdigest() != expected[1]):
                _fail('VENDOR_MISMATCH')
            return {'path': str(path), 'identity': _identity(info), 'sha256': h.hexdigest()}


def _utf8(data, code):
    try:
        text = data.decode('utf-8')
    except UnicodeError:
        _fail(code)
    if '\x00' in text or '\r' in text:
        _fail(code)
    return text


def _member(obs, path, name):
    with obs.opened(path, trusted=False) as (fd, _):
        with os.fdopen(os.dup(fd), 'rb') as stream, zipfile.ZipFile(stream) as archive:
            info = archive.getinfo(name)
            if info.file_size > TEXT_LIMIT:
                _fail('BOUNDS_EXCEEDED')
            value = archive.read(info)
            if _sha(value) != CLASS_HASHES[name]:
                _fail('VENDOR_MISMATCH')
            return value


def _class_constants(data):
    """Read UTF8 constants only after the containing class hash was verified."""
    if data[:4] != b'\xca\xfe\xba\xbe':
        _fail('PRODUCT_UNKNOWN')
    count = struct.unpack_from('>H', data, 8)[0]
    offset, index, matches = 10, 1, []
    widths = {3: 4, 4: 4, 5: 8, 6: 8, 7: 2, 8: 2, 9: 4, 10: 4,
              11: 4, 12: 4, 15: 3, 16: 2, 17: 4, 18: 4, 19: 2, 20: 2}
    while index < count:
        tag = data[offset]
        offset += 1
        if tag == 1:
            size = struct.unpack_from('>H', data, offset)[0]
            offset += 2
            value = data[offset:offset + size]
            offset += size
            matches.append(value)
        elif tag in widths:
            offset += widths[tag]
            index += int(tag in (5, 6))
        else:
            _fail('PRODUCT_UNKNOWN')
        index += 1
    return matches


def _embedded_metadata(data):
    matches = [value for value in _class_constants(data) if value.startswith(b'<component ')]
    if len(matches) != 1:
        _fail('PRODUCT_UNKNOWN')
    root = ET.fromstring(matches[0])
    namespace = '{http://jetbrains.org/intellij/schema/application-info}'
    names = root.find(namespace + 'names')
    build = root.find(namespace + 'build')
    if names is None or build is None or build.get('number') != 'IU-261.27258.48':
        _fail('PRODUCT_UNKNOWN')
    product, full, edition = names.get('product'), names.get('fullname'), names.get('edition')
    if product != 'IDEA' or full != 'IntelliJ IDEA' or edition is not None:
        _fail('PRODUCT_UNKNOWN')
    # getEditionName() returns null for the absent XML attribute. The generator
    # uses Java String concatenation, whose spelling is literally "null".
    stem = re.sub('[^a-z0-9]', '-', (product + '-' + ('null' if edition is None else edition)).lower())
    return full if edition is None else full + ' ' + edition, stem, _sha(matches[0])


@_step('VENDOR_METADATA')
def _vendor(obs, executable, idea):
    executable, idea = _exact_executable(executable), _path(idea)
    try:
        relative = executable.relative_to(idea).as_posix()
    except ValueError:
        _fail('EXECUTABLE_MISMATCH')
    if relative not in ('bin/idea', 'jbr/bin/java'):
        _fail('EXECUTABLE_MISMATCH')
    files = [obs.binary(idea / name, PINNED[name]) for name in (GENERATOR_JAR, CORE_JAR, relative)]
    generator = _member(obs, idea / GENERATOR_JAR, GENERATOR_CLASS)
    templates = [value for value in _class_constants(generator) if value.startswith(b'# This profile is autogenerated')]
    if len(templates) != 1 or _sha(templates[0]) != '679001e7d227bd53b25a5b6322f4c021076f871379a9ceac162d86911212cd3b':
        _fail('VENDOR_MISMATCH')
    full, stem, metadata_hash = _embedded_metadata(_member(obs, idea / CORE_JAR, NAMES_CLASS))
    text = templates[0].decode('utf-8') % (full, str(executable))
    return text, stem, files, metadata_hash


@_step('DESTINATION')
def _destination(obs, stem):
    for index in range(CANDIDATE_LIMIT):
        path = PROFILE_DIR / (stem + (f'-{index}' if index else ''))
        info = obs.entry(path)
        if info is None:
            return str(path), index + 1
        # Vendor follows symlinks and could choose a dangling one. Any symlink,
        # special entry, or untrusted prior candidate therefore fails closed.
        _trust(info)
    _fail('BOUNDS_EXCEEDED')


@_step('KERNEL_INVENTORY', 'INVENTORY_UNKNOWN')
def _inventory(obs, executable, installed=False):
    try:
        raw, _ = obs.read(INVENTORY)
        text = _utf8(raw, 'INVENTORY_UNKNOWN')
        if text and not text.endswith('\n'):
            _fail('INVENTORY_UNKNOWN')
        count, mode = 0, None
        for line in text.splitlines():
            name, separator, suffix = line.rpartition(' (')
            if (not separator or not name or len(name.encode()) > 4096
                    or any(ord(c) < 32 or ord(c) == 127 for c in name)
                    or not suffix.endswith(')') or suffix[:-1] not in MODES):
                _fail('INVENTORY_UNKNOWN')
            if name == str(executable):
                count += 1
                mode = suffix[:-1]
        # Unrelated names are never retained, hashed, or returned.
    except (OSError, ProfileError):
        _fail('INVENTORY_UNKNOWN')
    if installed:
        if count != 1 or mode != 'unconfined':
            _fail('LOADED_MISMATCH')
    elif count:
        _fail('PROFILE_COLLISION')
    return {'exact_name_count': count, 'mode': mode or 'ABSENT'}


@_step('INCLUDE_CLOSURE')
def _include_closure(obs, roots):
    records, visiting = {}, set()

    def visit(name, optional=False):
        if name not in INCLUDES or name in visiting:
            _fail('INCLUDE_UNKNOWN')
        if name in records:
            return
        selected = None
        absent = []
        for root in roots:
            path = _path(root) / name
            info = obs.entry(path)
            if info is None:
                absent.append(str(path))
                continue
            if not stat.S_ISREG(info.st_mode):
                _fail('INCLUDE_UNKNOWN')
            selected = path
            break
        if selected is None:
            if not optional:
                _fail('INCLUDE_UNKNOWN')
            records[name] = {'role': name, 'absent': absent}
            return
        raw, record = obs.read(selected, effective=True)
        records[name] = {'role': name, 'absent_before': absent, **record}
        visiting.add(name)
        for line in _utf8(raw, 'INCLUDE_UNKNOWN').splitlines():
            s = line.strip()
            if not s or (s.startswith('#') and not s.startswith('#include')):
                continue
            match = re.fullmatch(r'#?include\s+(if exists\s+)?<([A-Za-z0-9_./-]+)>\s*(?:#.*)?', s)
            if match:
                visit(match[2], bool(match[1]))
            elif re.search(r'\b(?:include|abi)\b', s) or '\\' in s:
                # No alternate spellings, continuation, recursive ABI imports,
                # variable paths, quoted paths, or directory expansion.
                _fail('INCLUDE_UNKNOWN')
            elif name == 'local/chrome':
                # A local override with policy rules needs review; a hash alone
                # would not establish the approved one-executable scope.
                _fail('INCLUDE_UNKNOWN')
            elif name.startswith('tunables/') and not re.fullmatch(r'@\{[A-Za-z][A-Za-z0-9_]*\}\s*\+?=\s*[^\x00]+', s):
                _fail('INCLUDE_UNKNOWN')
        visiting.remove(name)

    for name, optional in (('abi/4.0', False), ('tunables/global', False), ('local/chrome', True)):
        visit(name, optional)
    return list(records.values())


@_step('PARSER_CONFIG')
def _config(obs):
    """Supported AppArmor 4.0.1 options, not a general config interpreter."""
    info = obs.entry(CONFIG)
    if info is None:
        return [str(PROFILE_DIR)], False, {'path': str(CONFIG), 'absent': True}
    raw, record = obs.read(CONFIG, effective=True)
    base, roots, skip_cache = str(PROFILE_DIR), [], False
    no_value = {'write-cache', 'skip-cache', 'skip-read-cache', 'quiet', 'verbose',
                'show-cache', 'skip-bad-cache', 'skip-bad-cache-rebuild', 'abort-on-error'}
    for line in _utf8(raw, 'PARSER_CONTEXT_UNKNOWN').splitlines():
        value = line.strip()
        if not value or value.startswith('#'):
            continue
        if len(line.encode()) >= 255:
            _fail('PARSER_CONTEXT_UNKNOWN')
        if value in no_value:
            skip_cache |= value in ('skip-cache', 'skip-read-cache')
            continue
        match = re.fullmatch(r'(base|Include)[ \t=]+(/[A-Za-z0-9_./-]+)', value)
        if match:
            path = str(_path(match[2].rstrip('/')))
            try:
                with obs.directory(Path(path)):
                    pass
            except OSError:
                _fail('PARSER_CONTEXT_UNKNOWN')
            if match[1] == 'base':
                base = path
            else:
                roots.append(path)
            continue
        # Cache locations, forced ABI/mode/namespace, outputs and all unknown
        # options are unsupported. Never execute a parser with such a config.
        _fail('PARSER_CONTEXT_UNKNOWN')
    roots.append(base)  # upstream 4.0.1 parse_default_paths() appends basedir
    if len(roots) > 4 or len(set(roots)) != len(roots):
        _fail('PARSER_CONTEXT_UNKNOWN')
    return roots, skip_cache, record


def _run_read(obs, runner, command, env):
    if runner is None:
        _fail('PARSER_CONTEXT_UNKNOWN')
    obs.tick()
    # The owner supplies its sole-reaper runner. No subprocess/poll/wait here.
    try:
        result = runner(command, env=env, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                        timeout=max(0.001, obs.deadline - time.monotonic()), check=True)
        raw = result.stdout
    except Exception:
        _fail('PARSER_CONTEXT_UNKNOWN')
    obs.tick()
    if result.returncode != 0 or not isinstance(raw, bytes) or len(raw) > TEXT_LIMIT:
        _fail('PARSER_CONTEXT_UNKNOWN')
    return raw


def _provider_directory(obs, directory, records):
    """Only the two exact root usrmerge aliases may appear in provider PATH.

    Never follow the link: inspect its literal target under a held trusted root
    descriptor, then open the fixed target and every ancestor with O_NOFOLLOW.
    The alias's birth/metadata identity is retained for subsequent rechecks.
    """
    target = {'/bin': 'usr/bin', '/sbin': 'usr/sbin'}.get(directory)
    if target is None:
        return directory
    with obs.directory(Path('/')) as root:
        try:
            info = os.stat(directory[1:], dir_fd=root, follow_symlinks=False)
        except FileNotFoundError:
            return directory
        if not stat.S_ISLNK(info.st_mode):
            return directory  # ordinary directories retain the original checks
        _trust_distro_alias(info)
        if os.readlink(directory[1:], dir_fd=root) != target:
            _fail('PATH_UNSAFE')
        if _identity(os.stat(directory[1:], dir_fd=root, follow_symlinks=False)) != _identity(info):
            _fail('FILE_CHANGED')
        resolved = '/' + target
        with obs.directory(Path(resolved)):
            pass
        record = {'role': 'DISTRO_PATH_ALIAS', 'path': directory,
                  'target': target, 'identity': _identity(info)}
        existing = [row for row in records if row.get('role') == 'DISTRO_PATH_ALIAS' and row.get('path') == directory]
        if existing and existing != [record]:
            _fail('FILE_CHANGED')
        if not existing:
            records.append(record)
        return resolved


def _which(obs, name, directories, records):
    for directory in directories:
        path = _path(_provider_directory(obs, directory, records)) / name
        try:
            info = obs.entry(path, trusted='search')
        except FileNotFoundError:
            # Do not silently treat an inaccessible or linked ancestor as absent.
            _fail('PARSER_CONTEXT_UNKNOWN')
        if info is None:
            records.append({'path': str(path), 'absent': True, 'search_only': True})
            continue
        if info.st_mode & 0o111:
            _trust(info)
            record = obs.binary(path)
            records.append(record)
            return str(path)
        if not stat.S_ISREG(info.st_mode):
            _fail('PARSER_CONTEXT_UNKNOWN')
        records.append({'path': str(path), 'identity': _identity(info), 'search_only': True})
    return None


def _search_dirs(value):
    if not isinstance(value, str) or len(value) > 4096:
        _fail('PARSER_CONTEXT_UNKNOWN')
    directories = value.split(':')
    if not 1 <= len(directories) <= 16:
        _fail('PARSER_CONTEXT_UNKNOWN')
    for directory in directories:
        _exact_executable(directory)
    return directories


@_step('PROVIDER_ROUTE', 'PARSER_CONTEXT_UNKNOWN')
def _observe_parser(obs, runner, env, destination):
    """Observe a small supported normal route, without changing PATH/provider.

    Source contract: upstream AppArmor v4.0.1 parser_main.c and
    parser_include.c. Bind those defaults to the installed Ubuntu 4.0.1 package,
    its actual parser MD5/package manifest, SHA256, version and actual config.
    No raw helper output survives this function.
    """
    if not isinstance(env, dict) or env.get('LC_ALL', env.get('LANG', 'C')) not in ('C', 'C.UTF-8'):
        _fail('PARSER_CONTEXT_UNKNOWN')
    directories = _search_dirs(env.get('PATH'))
    records = []
    expected_helpers = {}
    if os.geteuid() == 0:
        route, parser_dirs = 'ROOT_DIRECT', directories
    else:
        # This order is pinned LocalSudoCommandProvider, not our preference.
        for provider in ('gksudo', 'kdesudo', 'pkexec'):
            if _which(obs, provider, directories, records):
                _fail('PARSER_CONTEXT_UNKNOWN')
        terminal = None
        for name in ('konsole', 'gnome-terminal', 'urxvt', 'xterm'):
            terminal = _which(obs, name, directories, records)
            if terminal:
                break
        sudo = _which(obs, 'sudo', directories, records)
        if not terminal or not sudo:
            _fail('PARSER_CONTEXT_UNKNOWN')
        for role, path in (('TERMINAL', terminal), ('SUDO', sudo)):
            verified = next(row for row in records if row.get('path') == path and 'sha256' in row)
            expected_helpers[role] = {'path': path, 'identity': list(verified['identity']),
                                      'sha256': verified['sha256']}
        # The existing family authority may register this single verified sudo
        # probe before its managed launch. Ordinary runner functions are not
        # wrapped or replaced, and this never authorizes a different command.
        expect_probe = getattr(getattr(runner, '__self__', None), 'expect_sudo_probe', None)
        if expect_probe is not None:
            if not callable(expect_probe):
                _fail('PARSER_CONTEXT_UNKNOWN')
            helper = expected_helpers['SUDO']
            try:
                expect_probe({**helper, 'identity': list(helper['identity'])})
            except Exception:
                _fail('PARSER_CONTEXT_UNKNOWN')
        raw = _run_read(obs, runner, [sudo, '-n', '-l'], env)
        listing = _utf8(raw, 'PARSER_CONTEXT_UNKNOWN')
        paths = re.findall(r'\bsecure_path=([^\s,]+)', listing)
        if (len(paths) != 1 or not re.search(r'\(ALL(?:\s*:\s*ALL)?\)\s+NOPASSWD:\s+ALL\s*$', listing)
                or any(token in listing for token in ('SETENV:', 'env_keep', 'env_file', 'exempt_group', 'Defaults!'))):
            _fail('PARSER_CONTEXT_UNKNOWN')
        parser_dirs, route = _search_dirs(paths[0]), 'TERMINAL_SUDO'
        # Hash only; do not retain usernames, hostnames, or sudo rule contents.
        records.append({'role': 'SUDO_LIST', 'sha256': _sha(raw)})
    parser = _which(obs, 'apparmor_parser', parser_dirs, records)
    if parser != '/usr/sbin/apparmor_parser':
        _fail('PARSER_CONTEXT_UNKNOWN')
    with _step('PACKAGE_IDENTITY'):
        # Read the fixed official package manifest directly, never query all policy.
        manifest_path = Path('/var/lib/dpkg/info/apparmor.md5sums')
        manifest_raw, manifest = obs.read(manifest_path, effective=True)
        rows = re.findall(rb'^([0-9a-f]{32})  usr/sbin/apparmor_parser$', manifest_raw, re.MULTILINE)
        if len(rows) != 1:
            _fail('PARSER_CONTEXT_UNKNOWN')
        with obs.opened(Path(parser)) as (fd, _):
            digest = hashlib.md5(usedforsecurity=False)
            count = 0
            while True:
                obs.tick()
                chunk = os.read(fd, 65536)
                if not chunk:
                    break
                count += len(chunk)
                if count > 16 * 1024 * 1024:
                    _fail('BOUNDS_EXCEEDED')
                digest.update(chunk)
        if digest.hexdigest().encode() != rows[0]:
            _fail('PARSER_CONTEXT_UNKNOWN')
        records.append(manifest)
        query = Path('/usr/bin/dpkg-query')
        records.append(obs.binary(query))
        package = _run_read(obs, runner, [str(query), '-W', '-f=${Status}\t${Version}\t${Architecture}\n', 'apparmor'], env)
        if not re.fullmatch(rb'install ok installed\t4\.0\.1-0ubuntu[0-9.a-z+~]+\tamd64\n', package):
            _fail('PARSER_CONTEXT_UNKNOWN')
    roots, skip_cache, config = _config(obs)
    records.append(config)
    with _step('PARSER_CONFIG'):
        # AppArmor 4.0.1 process_profile() also consults these exact basename
        # switches. Even a dangling link is not a safe new policy destination.
        for switch in ('disable', 'force-complain'):
            path = Path(roots[-1]) / switch / Path(destination).name
            if obs.entry(path) is not None:
                _fail('PARSER_CONTEXT_UNKNOWN')
            records.append({'path': str(path), 'absent': True})
    with _step('PARSER_VERSION'):
        version = _run_read(obs, runner, [parser, '--version'], env)
        if not version.startswith(b'AppArmor parser version 4.0.1\n'):
            _fail('PARSER_CONTEXT_UNKNOWN')
    with _step('PARSER_CONFIG'):
        # print-config-file itself does not exit: --version makes this a bounded,
        # non-loading observation after printing the actual default config path.
        config_output = _run_read(obs, runner, [parser, '--print-config-file', '--version'], env)
        if config_output != str(CONFIG).encode() + b'\n' + version:
            _fail('PARSER_CONTEXT_UNKNOWN')
    with _step('CACHE_LOCATION'):
        cache_paths = []
        if not skip_cache:
            cache_raw = _run_read(obs, runner, [parser, '--print-cache-dir'], env)
            cache_lines = _utf8(cache_raw, 'PARSER_CONTEXT_UNKNOWN').splitlines()
            if len(cache_lines) != 1 or not re.fullmatch(r'/var/cache/apparmor/[A-Za-z0-9_.-]+', cache_lines[0]):
                _fail('PARSER_CONTEXT_UNKNOWN')
            cache_paths = [str(Path(cache_lines[0]) / Path(destination).name)]
    return {'route': route, 'path_sha256': _sha(env['PATH'].encode()),
            'roots': roots, 'files': records, 'cache_paths': cache_paths,
            'expected_helpers': expected_helpers,
            'package_sha256': _sha(package), 'version_sha256': _sha(version),
            'parser_sha256': next(r['sha256'] for r in records if r.get('path') == parser),
            'defaults': 'UBUNTU_APPARMOR_4_0_1'}


@_step('PROVIDER_ROUTE', 'PARSER_CONTEXT_UNKNOWN')
def observe_parser_context(destination, *, runner, env=None, filesystem_root=Path('/')):
    """Read-only context observation through the caller's supervised runner."""
    try:
        return _observe_parser(_Observation(filesystem_root), runner,
                               dict(os.environ) if env is None else env, _path(destination))
    except ProfileError:
        raise
    except (OSError, ValueError, TypeError):
        _fail('PARSER_CONTEXT_UNKNOWN')


@_step('CACHE_LOCATION')
def _cache_absent(obs, context):
    for value in context['cache_paths']:
        path = _path(value)
        try:
            info = obs.entry(path)
        except FileNotFoundError:
            # An absent feature-cache directory is acceptable only when its
            # existing parent was itself checked without following links.
            with obs.directory(path.parent.parent):
                parent = obs.entry(path.parent)
            if parent is not None:
                _fail('PARSER_CONTEXT_UNKNOWN')
            continue
        if info is not None:
            _fail('PROFILE_COLLISION')


@_step('PROVIDER_ROUTE')
def _snapshots(obs, records):
    for record in records:
        if 'path' not in record:
            continue
        if record.get('role') == 'DISTRO_PATH_ALIAS':
            observed = []
            _provider_directory(obs, record['path'], observed)
            if observed != [record]:
                _fail('FILE_CHANGED')
            continue
        path = _path(record['path'])
        step = 'PROVIDER_ROUTE'
        if path == CONFIG or path.parent.name in ('disable', 'force-complain'):
            step = 'PARSER_CONFIG'
        elif str(path) in ('/var/lib/dpkg/info/apparmor.md5sums', '/usr/bin/dpkg-query', '/usr/sbin/apparmor_parser'):
            step = 'PACKAGE_IDENTITY'
        with _step(step):
            info = obs.entry(path, trusted='search' if record.get('search_only') else True)
            if record.get('absent'):
                if info is not None:
                    _fail('FILE_CHANGED')
            elif info is None or _identity(info) != record['identity']:
                _fail('FILE_CHANGED')
            elif 'sha256' in record:
                fresh = obs.binary(path)
                if fresh['sha256'] != record['sha256']:
                    _fail('FILE_CHANGED')


@_step('CANDIDATE', 'CANDIDATE_INVALID')
def _validate_candidate(candidate):
    try:
        if (not isinstance(candidate, dict) or type(candidate['schema']) is not int or candidate['schema'] != 1
                or len(_canonical(candidate)) > TOTAL_LIMIT
                or _sha(_canonical({k: v for k, v in candidate.items() if k != 'seal'})) != candidate['seal']):
            _fail('CANDIDATE_INVALID')
        for value in (candidate['metadata_sha256'], candidate['seal'],
                      *(row['sha256'] for row in candidate['vendor'])):
            if not isinstance(value, str) or not re.fullmatch('[0-9a-f]{64}', value):
                _fail('CANDIDATE_INVALID')
        for key in ('executable', 'idea', 'expected_utf8', 'destination', 'stem'):
            if not isinstance(candidate[key], str):
                _fail('CANDIDATE_INVALID')
        for key, maximum in (('candidate_checks', CANDIDATE_LIMIT), ('effective_files', FILE_LIMIT),
                             ('effective_bytes', TOTAL_LIMIT)):
            if type(candidate[key]) is not int or not 0 <= candidate[key] <= maximum:
                _fail('CANDIDATE_INVALID')
        if (len(candidate['vendor']) != 3 or len(candidate['includes']) > len(INCLUDES)
                or len(candidate['expected_utf8'].encode()) > TEXT_LIMIT):
            _fail('CANDIDATE_INVALID')
    except (KeyError, ValueError, TypeError, IndexError, AttributeError):
        _fail('CANDIDATE_INVALID')


@_step('CANDIDATE')
def prepare(executable, idea, *, runner=None, env=None, filesystem_root=Path('/')):
    """Return a private bounded JSON candidate; no state outside this object is written."""
    obs = _Observation(filesystem_root)
    try:
        with _step('VENDOR_METADATA'):
            executable, idea = _exact_executable(executable), _path(idea)
        text, stem, vendor, metadata = _vendor(obs, executable, idea)
        destination, count = _destination(obs, stem)
        _inventory(obs, executable)
        context = _observe_parser(obs, runner, dict(os.environ) if env is None else env, destination)
        _cache_absent(obs, context)
        includes = _include_closure(obs, context['roots'])
        candidate = {'schema': 1, 'executable': str(executable), 'idea': str(idea),
                     'expected_utf8': text, 'destination': destination, 'stem': stem,
                     'candidate_checks': count, 'vendor': vendor, 'metadata_sha256': metadata,
                     'parser': context, 'includes': includes, 'effective_files': len(obs.texts),
                     'effective_bytes': sum(obs.texts.values())}
        candidate['seal'] = _sha(_canonical(candidate))
        obs.tick()
        _validate_candidate(candidate)
        return candidate
    except ProfileError:
        raise
    except (OSError, ValueError, TypeError, KeyError, IndexError, struct.error, zipfile.BadZipFile, ET.ParseError):
        _fail('FILE_UNKNOWN')


def _unchanged(obs, candidate, executable, *, runner=None, env=None):
    _validate_candidate(candidate)
    if str(_exact_executable(executable)) != candidate['executable']:
        _fail('EXECUTABLE_MISMATCH', step='VENDOR_METADATA')
    text, stem, vendor, metadata = _vendor(obs, executable, _path(candidate['idea']))
    if (text != candidate['expected_utf8'] or stem != candidate['stem']
            or vendor != candidate['vendor'] or metadata != candidate['metadata_sha256']):
        _fail('FILE_CHANGED', step='VENDOR_METADATA')
    context = candidate['parser']
    actual_env = dict(os.environ) if env is None else env
    if _sha(actual_env.get('PATH', '').encode()) != context['path_sha256']:
        _fail('PARSER_CONTEXT_UNKNOWN', step='PROVIDER_ROUTE')
    _snapshots(obs, context['files'])
    if runner is not None and _observe_parser(obs, runner, actual_env, candidate['destination']) != context:
        _fail('PARSER_CONTEXT_UNKNOWN', step='PROVIDER_ROUTE')
    roots, _, _ = _config(obs)
    if roots != context['roots']:
        _fail('FILE_CHANGED', step='PARSER_CONFIG')
    if _include_closure(obs, roots) != candidate['includes']:
        _fail('FILE_CHANGED', step='INCLUDE_CLOSURE')


@_step('PROVIDER_FRESHNESS')
def _write_receipt(obs, candidate, receipt_path):
    path = _path(receipt_path)
    receipt = {'schema': 1, 'status': 'PROVIDER_OBSERVED', 'candidate_sha256': candidate['seal'],
               'parser_context_sha256': _sha(_canonical(candidate['parser'])),
               'issued_ns': time.monotonic_ns(), 'nonce': secrets.token_hex(16)}
    raw = _canonical(receipt)
    with obs.directory(path.parent, trusted=False) as directory:
        parent = os.fstat(directory)
        if parent.st_uid != os.getuid() or parent.st_mode & 0o077:
            _fail('PATH_UNSAFE')
        fd = os.open(path.name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                     0o600, dir_fd=directory)
        try:
            if os.write(fd, raw) != len(raw):
                _fail('FILE_UNKNOWN')
        finally:
            os.close(fd)


@_step('PROVIDER_FRESHNESS', 'PARSER_CONTEXT_UNKNOWN')
def _read_receipt(obs, candidate, receipt_path):
    with obs.opened(_path(receipt_path), trusted=False) as (fd, info):
        if (info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o600
                or info.st_nlink != 1 or info.st_size > 4096):
            _fail('PARSER_CONTEXT_UNKNOWN')
        raw = os.read(fd, 4097)
    try:
        receipt = json.loads(raw)
        if (set(receipt) != {'schema', 'status', 'candidate_sha256', 'parser_context_sha256', 'issued_ns', 'nonce'}
                or receipt['schema'] != 1 or receipt['status'] != 'PROVIDER_OBSERVED'
                or receipt['candidate_sha256'] != candidate['seal']
                or receipt['parser_context_sha256'] != _sha(_canonical(candidate['parser']))
                or type(receipt['issued_ns']) is not int
                or not 0 <= time.monotonic_ns() - receipt['issued_ns'] <= OBSERVATION_SECONDS * 1_000_000_000
                or not re.fullmatch('[0-9a-f]{32}', receipt['nonce'])):
            _fail('PARSER_CONTEXT_UNKNOWN')
    except (ValueError, TypeError, KeyError):
        _fail('PARSER_CONTEXT_UNKNOWN')


@_step('CANDIDATE')
def recheck_before(candidate, executable, *, runner=None, env=None, receipt_path=None, filesystem_root=Path('/')):
    """Immediately before the normal GUI click; no cached 'absent' decisions."""
    obs = _Observation(filesystem_root)
    try:
        _validate_candidate(candidate)
        if candidate['parser']['route'] == 'TERMINAL_SUDO' and runner is None:
            _fail('PARSER_CONTEXT_UNKNOWN', step='PROVIDER_ROUTE')
        _unchanged(obs, candidate, executable, runner=runner, env=env)
        destination, count = _destination(obs, candidate['stem'])
        if destination != candidate['destination'] or count != candidate['candidate_checks']:
            _fail('DESTINATION_CHANGED', step='DESTINATION')
        _cache_absent(obs, candidate['parser'])
        _inventory(obs, executable)
        if receipt_path is not None:
            _write_receipt(obs, candidate, receipt_path)
        return {**public_evidence(candidate), 'status': 'PREINSTALL_VERIFIED'}
    except ProfileError:
        raise
    except (OSError, ValueError, TypeError, KeyError):
        _fail('FILE_UNKNOWN')


@_step('CANDIDATE', 'PARSER_CONTEXT_UNKNOWN')
def recheck_snapshot(candidate, executable, *, receipt_path, env=None, filesystem_root=Path('/')):
    """Companion-only pure read following a fresh primary managed observation.

    The primary creates the fixed receipt in its private 0700 stage directory;
    the companion accepts only its exact candidate/parser binding within five
    seconds and rereads all actionable file/kernel facts. It runs no helper and
    does not transform an arbitrary boolean into provider-resolution authority.
    """
    obs = _Observation(filesystem_root)
    try:
        _validate_candidate(candidate)
        _read_receipt(obs, candidate, receipt_path)
        _unchanged(obs, candidate, executable, env=env)
        destination, count = _destination(obs, candidate['stem'])
        if destination != candidate['destination'] or count != candidate['candidate_checks']:
            _fail('DESTINATION_CHANGED', step='DESTINATION')
        _cache_absent(obs, candidate['parser'])
        _inventory(obs, executable)
        _read_receipt(obs, candidate, receipt_path)  # slow checks cannot extend freshness
        return {**public_evidence(candidate), 'status': 'PREINSTALL_VERIFIED'}
    except ProfileError:
        raise
    except (OSError, ValueError, TypeError, KeyError):
        _fail('PARSER_CONTEXT_UNKNOWN')


@_step('INSTALLED_BYTES')
def verify_installed(candidate, *, runner=None, env=None, filesystem_root=Path('/')):
    obs = _Observation(filesystem_root)
    try:
        _unchanged(obs, candidate, candidate['executable'], runner=runner, env=env)
        raw, _ = obs.read(_path(candidate['destination']))
        if raw != candidate['expected_utf8'].encode('utf-8'):
            _fail('INSTALLED_MISMATCH')
        _inventory(obs, candidate['executable'], installed=True)
        return {**public_evidence(candidate), 'status': 'INSTALLED_VERIFIED', 'exact_name_count': 1}
    except ProfileError:
        raise
    except (OSError, ValueError, TypeError, KeyError):
        _fail('FILE_UNKNOWN')


def public_evidence(candidate):
    """The entire public allowlist. No caller-controlled free text is returned."""
    _validate_candidate(candidate)
    return {'status': 'PROSPECTIVE_VERIFIED', 'mode': 'unconfined', 'userns': True,
            'destination_role': 'VENDOR_APPARMOR_PROFILE',
            'destination_sha256': _sha(candidate['destination'].encode()),
            'profile_sha256': _sha(candidate['expected_utf8'].encode()),
            'profile_name_sha256': _sha(candidate['executable'].encode()),
            'executable_sha256': candidate['vendor'][2]['sha256'],
            'generator_sha256': candidate['vendor'][0]['sha256'],
            'metadata_sha256': candidate['metadata_sha256'],
            'include_manifest_sha256': _sha(_canonical(candidate['includes'])),
            'parser_context_sha256': _sha(_canonical(candidate['parser'])),
            'candidate_sha256': candidate['seal'], 'candidate_checks': candidate['candidate_checks'],
            'effective_files': candidate['effective_files'], 'effective_bytes': candidate['effective_bytes']}


@_step('ACTIVE_CONTEXT', 'CONTEXT_UNKNOWN')
def verify_context(pid, expected_executable, *, filesystem_root=Path('/')):
    """Read only the caller-owned PID; caller must bracket with pidfd identity.

    LSM_ATTR_CURRENT is active context (kernel userspace-api/lsm.html). Prefer
    its explicit AppArmor interface; only ENOENT permits the legacy fallback.
    """
    if type(pid) is not int or pid <= 0:
        _fail('CONTEXT_UNKNOWN')
    expected = str(_exact_executable(expected_executable))
    obs = _Observation(filesystem_root)
    paths = (Path(f'/proc/{pid}/attr/apparmor/current'), Path(f'/proc/{pid}/attr/current'))
    try:
        try:
            raw, _ = obs.read(paths[0], trusted=False, limit=8192)
            role = 'APPARMOR_CURRENT'
        except FileNotFoundError:
            raw, _ = obs.read(paths[1], trusted=False, limit=8192)
            role = 'LSM_CURRENT'
        text = _utf8(raw, 'CONTEXT_UNKNOWN')
    except (OSError, ProfileError):
        _fail('CONTEXT_UNKNOWN')
    if text not in (expected + ' (unconfined)', expected + ' (unconfined)\n'):
        _fail('CONTEXT_MISMATCH')
    return {'status': 'CONTEXT_VERIFIED', 'interface': role, 'mode': 'unconfined',
            'profile_name_sha256': _sha(expected.encode()), 'context_sha256': _sha(raw)}
