"""Private bundled-JBR title compatibility prerequisite, never IDE acceptance.

The workflow runs this after its checksum-verified pinned IDEA installation.
The two AWT windows live on a separate authenticated Xvfb. Only their modern
title properties are removed to expose the WM_NAME values written by AWT.
The production selector handles all reads and encoding validation. The sole
wrong-type write targets a synthetic window created by the short-lived probe.
"""
from pathlib import Path
import ctypes as C
import errno
import hashlib
import json
import os
import re
import select
import signal
import stat
import struct
import subprocess
import sys
import tempfile
import time

import modal_window
from display_diagnostic import encode, json_read, publish
from safe_io import BoundaryError, absolute, read_regular, regular_reader, validate_directory

R = Path(__file__).resolve().parent
NAME = 'awt-title-fixture.json'
KIND = 'PRIVATE_BUNDLED_JBR_AWT_TITLE_COMPATIBILITY_NOT_IDE_OR_ACCEPTANCE'
BINARY = Path('/usr/bin/Xvfb')
HELPER = R / 'probes/AwtTitleFixture.java'
RUNTIME_VERSION = '25.0.4+1-b329.128'
IDEA_VERSION = '2026.1.5'
IDEA_BUILD = '261.27258.48'
IDEA_ARCHIVE_SHA256 = 'b60483784c4051e72f852529d40bc7ab6c52e5fd791a088dea455a254473e4ce'
ACTIVITY_SECONDS = 40
PROBE_SECONDS = 2
DISPLAY = ':7998'
TITLES = (b'Academy AWT title fixture ASCII',
          'Academy AWT title fixture \u4e2d\u6587\u6807\u9898'.encode('utf-8'))
MODERN_HASHES = tuple(modal_window._title_digest(b'_NET_WM_NAME', b'UTF8_STRING', raw)
                      for raw in TITLES)
CASE_NAMES = ('awt_modern_ascii', 'awt_modern_non_latin', 'awt_legacy_ascii',
              'awt_legacy_non_latin', 'owned_synthetic_wrong_type')
ERRORS = ('PRECHECK_UNAVAILABLE', 'XVFB_START_UNAVAILABLE', 'JVM_START_UNAVAILABLE',
          'JVM_EXITED', 'PROBE_FAILED', 'PROBE_TIMEOUT', 'BUDGET_EXHAUSTED',
          'CANCELLED', 'CLEANUP_UNVERIFIED')
HASH_NAMES = ('toolchain_sha256', 'fixture_sha256', 'helper_sha256', 'selector_sha256',
              'release_sha256', 'java_sha256', 'libjvm_sha256', 'libawt_xawt_sha256')
PRECHECK_STEPS = ('ROOT_BINDING', 'ROOT_DIRECTORY', 'PINS_READ', 'PINS_JSON', 'PINS_IDENTITY',
                  'PRODUCT_READ', 'PRODUCT_JSON', 'PRODUCT_IDENTITY', 'RELEASE_READ',
                  'RELEASE_VERSION', 'JAVA_EXECUTABLE',
                  *('HASH_' + name.removesuffix('_sha256').upper() for name in HASH_NAMES),
                  'RUNTIME_SCHEMA', 'PIDFD_CAPABILITY', 'XVFB_BINARY', 'DISPLAY_AVAILABLE',
                  'PRIVATE_DIRECTORY', 'AUTHORITY_CREATE')
PRECHECK_CLASSES = ('FileNotFoundError', 'PermissionError', 'NotADirectoryError',
                    'IsADirectoryError', 'BoundaryError', 'OSError', 'UnicodeDecodeError',
                    'JSONDecodeError', 'KeyError', 'TypeError', 'ValueError',
                    'TimeoutError', 'InterruptedError', 'KeyboardInterrupt', 'OTHER_EXCEPTION')
PRECHECK_REASONS = ('MISSING', 'PERMISSION', 'PATH_OR_FILE_BOUNDARY', 'INVALID_JSON',
                   'INVALID_UTF8', 'REQUIRED_FIELD', 'CONDITION_REJECTED', 'IO_ERROR',
                   'CANCELLED', 'TIMEOUT', 'UNEXPECTED_EXCEPTION')


def _identity_token(value):
    # Numeric vendor version/build tokens only; never arbitrary release-file text.
    if type(value) is not str or len(value) > 64:
        return None
    pattern = r'[0-9]{1,4}(?:\.[0-9]{1,5}){0,3}(?:-(?:ea|internal))?(?:\+[0-9]{1,4}(?:-b[0-9]{1,4}(?:\.[0-9]{1,4}){0,2})?)?'
    return value if re.fullmatch(pattern, value) else None


def precheck_document(value):
    _closed(value, ('step', 'reason', 'exception_class', 'facts'))
    for key, allowed in (('step', PRECHECK_STEPS), ('reason', PRECHECK_REASONS),
                         ('exception_class', PRECHECK_CLASSES)):
        require(type(value[key]) is str and value[key] in allowed)
    facts = value['facts']
    require(type(facts) is dict and len(facts) <= 10)
    for key, item in facts.items():
        require(type(key) is str)
        if key in ('regular', 'size_capped', 'within_limit', 'identity_matches', 'executable', 'hash_complete'):
            require(type(item) is bool)
        elif key in ('observed_version', 'observed_build'):
            require(item is None or (type(item) is str and _identity_token(item) == item))
        elif key == 'metadata_sha256':
            _token(item, r'[0-9a-f]{64}')
        elif key == 'version_field_count':
            require(type(item) is int and 0 <= item <= 16)
        elif key == 'size_bytes':
            require(type(item) is int and 0 <= item <= 2 ** 31 - 1)
        else:
            raise ValueError('INVALID_PRECHECK_FACT')
    return {**value, 'facts': dict(facts)}


class PrecheckFailure(ValueError):
    def __init__(self, step, error, facts):
        kind = type(error).__name__
        reason = ('CANCELLED' if isinstance(error, (InterruptedError, KeyboardInterrupt)) else
                  'TIMEOUT' if isinstance(error, TimeoutError) else
                  'MISSING' if isinstance(error, FileNotFoundError) else
                  'PERMISSION' if isinstance(error, PermissionError) else
                  'PATH_OR_FILE_BOUNDARY' if isinstance(error, (BoundaryError, NotADirectoryError, IsADirectoryError))
                  or (isinstance(error, OSError) and error.errno in (errno.ELOOP, errno.ENOTDIR)) else
                  'INVALID_JSON' if isinstance(error, json.JSONDecodeError) else
                  'INVALID_UTF8' if isinstance(error, UnicodeDecodeError) else
                  'REQUIRED_FIELD' if isinstance(error, KeyError) else
                  'IO_ERROR' if isinstance(error, OSError) else
                  'CONDITION_REJECTED' if isinstance(error, (ValueError, TypeError)) else
                  'UNEXPECTED_EXCEPTION')
        self.document = precheck_document({'step': step, 'reason': reason,
            'exception_class': kind if kind in PRECHECK_CLASSES else 'OTHER_EXCEPTION', 'facts': facts})
        super().__init__('AWT_TITLE_PRECHECK_FAILED')


def _checked(step, action, facts=None):
    facts = {} if facts is None else facts
    try:
        return action()
    except PrecheckFailure:
        raise
    except BaseException as error:
        raise PrecheckFailure(step, error, facts) from error


def _condition(step, matched, **facts):
    facts['identity_matches'] = bool(matched)
    _checked(step, lambda: require(matched), facts)


def _checked_read(step, path, limit):
    facts = {}
    def read():
        with regular_reader(path) as stream:
            size = os.fstat(stream.fileno()).st_size
            facts.update(regular=True, size_bytes=min(size, 2 ** 31 - 1),
                         size_capped=size > 2 ** 31 - 1, within_limit=size <= limit)
            require(size <= limit)
            raw = stream.read(limit + 1)
            require(len(raw) == size and len(raw) <= limit)
            return raw
    return _checked(step, read, facts)


def require(ok):
    if not ok:
        raise ValueError('AWT_TITLE_FIXTURE_BOUNDARY')


def _token(value, pattern):
    require(type(value) is str and re.fullmatch(pattern, value) is not None)
    return value


def _closed(value, fields):
    require(type(value) is dict and len(value) == len(fields))
    require(all(type(key) is str for key in value) and set(value) == set(fields))


def _cases(value):
    require(type(value) is list and len(value) <= len(CASE_NAMES))
    result = []
    for index, item in enumerate(value):
        _closed(item, ('case', 'status', 'title_sha256', 'title_encoding'))
        require(type(item['case']) is str and item['case'] == CASE_NAMES[index])
        require(type(item['status']) is str and item['status'] == ('REJECTED' if index == 4 else 'PASS'))
        digest = item['title_sha256']
        if index == 4:
            require(digest is None and item['title_encoding'] is None)
        else:
            _token(digest, r'[0-9a-f]{64}')
            require(type(item['title_encoding']) is str)
            if index < 2:
                require(digest == MODERN_HASHES[index] and item['title_encoding'] == 'UTF8_STRING')
            else:
                require(digest != MODERN_HASHES[index - 2]
                        and item['title_encoding'] in ('STRING', 'UTF8_STRING', 'COMPOUND_TEXT'))
        result.append(dict(item))
    return result


def _runtime(value):
    if value is None:
        return None
    _closed(value, ('idea_version', 'idea_build', 'idea_archive_sha256',
                    'java_runtime_version', 'hashes'))
    for name, expected in (('idea_version', IDEA_VERSION), ('idea_build', IDEA_BUILD),
                           ('idea_archive_sha256', IDEA_ARCHIVE_SHA256)):
        require(type(value[name]) is str and value[name] == expected)
    require(value['java_runtime_version'] is None or
            (type(value['java_runtime_version']) is str and value['java_runtime_version'] == RUNTIME_VERSION))
    _closed(value['hashes'], HASH_NAMES)
    hashes = {key: _token(value['hashes'][key], r'[0-9a-f]{64}') for key in HASH_NAMES}
    return {**value, 'hashes': hashes}


def report_document(value):
    """Closed public artifact: typed codes and hashes, no paths, titles or logs."""
    _closed(value, ('schema', 'status', 'kind', 'cases', 'cleanup', 'exit_codes', 'error', 'diagnosis',
                    'runtime', 'precheck_failure', 'run_id', 'run_attempt', 'tested_sha', 'elapsed_milliseconds'))
    require(type(value['schema']) is int and value['schema'] == 1)
    require(type(value['status']) is str and value['status'] in ('PASS', 'FAIL'))
    require(type(value['kind']) is str and value['kind'] == KIND)
    require(value['error'] is None or (type(value['error']) is str and value['error'] in ERRORS))
    for key, pattern in (('run_id', r'[1-9][0-9]{0,19}'), ('run_attempt', r'[1-9][0-9]{0,19}'),
                         ('tested_sha', r'[0-9a-f]{40}')):
        _token(value[key], pattern)
    require(type(value['elapsed_milliseconds']) is int and 0 <= value['elapsed_milliseconds'] <= 60000)
    _closed(value['cleanup'], ('jvm', 'xvfb'))
    for status in value['cleanup'].values():
        require(type(status) is str and status in ('NOT_STARTED', 'REAPED', 'UNVERIFIED'))
    _closed(value['exit_codes'], ('jvm', 'xvfb'))
    for child, code in value['exit_codes'].items():
        require(code is None or (type(code) is int and -128 <= code <= 255))
        if value['cleanup'][child] == 'NOT_STARTED':
            require(code is None)
        if value['cleanup'][child] == 'REAPED':
            require(type(code) is int)
    result = {**value, 'cases': _cases(value['cases']), 'cleanup': dict(value['cleanup']),
              'exit_codes': dict(value['exit_codes']),
              'runtime': _runtime(value['runtime']),
              'precheck_failure': None if value['precheck_failure'] is None else precheck_document(value['precheck_failure']),
              'diagnosis': None if value['diagnosis'] is None else modal_window.failure_document(value['diagnosis'])}
    if result['status'] == 'PASS':
        require(len(result['cases']) == len(CASE_NAMES) and result['error'] is None and result['diagnosis'] is None
                and result['precheck_failure'] is None)
        require(all(status == 'REAPED' for status in result['cleanup'].values()))
        require(result['runtime'] is not None and result['runtime']['java_runtime_version'] == RUNTIME_VERSION)
    else:
        require(result['error'] is not None)
    if result['error'] == 'PRECHECK_UNAVAILABLE':
        require(result['precheck_failure'] is not None)
    if result['precheck_failure'] is not None:
        require(result['status'] == 'FAIL' and not result['cases']
                and all(s == 'NOT_STARTED' for s in result['cleanup'].values()))
    if result['cases']:
        require(result['runtime'] is not None and result['runtime']['java_runtime_version'] == RUNTIME_VERSION)
    if 'UNVERIFIED' in result['cleanup'].values():
        require(result['status'] == 'FAIL' and result['error'] == 'CLEANUP_UNVERIFIED')
    require(len(encode(result)) <= 8192)
    return result


def _remaining(deadline, cap):
    left = deadline - time.monotonic()
    if left <= 0:
        raise TimeoutError('FIXTURE_BUDGET')
    return min(left, cap)


def _hash_file(path, cap, facts=None):
    # Reject symlinks in every path component; bound both size and total read.
    with regular_reader(path) as stream:
        size = os.fstat(stream.fileno()).st_size
        if facts is not None:
            facts.update(regular=True, size_bytes=min(size, 2 ** 31 - 1),
                         size_capped=size > 2 ** 31 - 1, within_limit=0 < size <= cap, hash_complete=False)
        require(0 < size <= cap)
        digest = hashlib.sha256()
        total = 0
        while True:
            data = stream.read(min(1024 * 1024, cap + 1 - total))
            if not data:
                break
            total += len(data)
            require(total <= cap)
            digest.update(data)
        require(total == size)
        if facts is not None:
            facts['hash_complete'] = True
        return digest.hexdigest()


def _runtime_identity(toolchain_root):
    def root_binding():
        root = absolute(toolchain_root)
        runner = absolute(os.environ['RUNNER_TEMP'])
        require(root == absolute(os.environ['TOOLCHAIN_DIR']) and root != runner and root.is_relative_to(runner))
        return root
    root = _checked('ROOT_BINDING', root_binding)
    _checked('ROOT_DIRECTORY', lambda: validate_directory(root))
    raw_pins = _checked_read('PINS_READ', R / 'toolchain.json', 16384)
    pins = _checked('PINS_JSON', lambda: json_read(raw_pins))
    _checked('PINS_IDENTITY', lambda: _condition('PINS_IDENTITY',
        pins['idea']['version'] == IDEA_VERSION and pins['idea']['build'] == IDEA_BUILD
        and pins['idea']['sha256'] == IDEA_ARCHIVE_SHA256))
    idea = root / 'idea'
    raw_info = _checked_read('PRODUCT_READ', idea / 'product-info.json', 65536)
    info = _checked('PRODUCT_JSON', lambda: json_read(raw_info))
    product_facts = {'metadata_sha256': hashlib.sha256(raw_info).hexdigest(), 'size_bytes': len(raw_info),
                     'observed_version': _identity_token(info.get('version')) if type(info) is dict else None,
                     'observed_build': _identity_token(info.get('buildNumber')) if type(info) is dict else None}
    _checked('PRODUCT_IDENTITY', lambda: _condition('PRODUCT_IDENTITY',
        info['version'] == IDEA_VERSION and info['buildNumber'] == IDEA_BUILD, **product_facts), product_facts)
    release = _checked_read('RELEASE_READ', idea / 'jbr/release', 16384)
    # The live JVM separately verifies the complete runtime version before READY.
    versions = re.findall(rb'^JAVA_VERSION="([^"]+)"$', release, flags=re.M)
    observed = _identity_token(versions[0].decode('ascii', errors='replace')) if len(versions) == 1 else None
    _condition('RELEASE_VERSION', versions == [b'25.0.4'], observed_version=observed,
               version_field_count=min(len(versions), 16), size_bytes=len(release),
               metadata_sha256=hashlib.sha256(release).hexdigest())
    java = idea / 'jbr/bin/java'
    def executable():
        regular = stat.S_ISREG(java.lstat().st_mode)
        allowed = os.access(java, os.X_OK)
        _condition('JAVA_EXECUTABLE', regular and allowed, regular=regular, executable=allowed)
    _checked('JAVA_EXECUTABLE', executable)
    files = {'toolchain_sha256': (R / 'toolchain.json', 16384),
             'fixture_sha256': (Path(__file__), 65536), 'helper_sha256': (HELPER, 16384),
             'selector_sha256': (R / 'modal_window.py', 128 * 1024),
             'release_sha256': (idea / 'jbr/release', 16384),
             'java_sha256': (java, 4 * 1024 * 1024),
             'libjvm_sha256': (idea / 'jbr/lib/server/libjvm.so', 128 * 1024 * 1024),
             'libawt_xawt_sha256': (idea / 'jbr/lib/libawt_xawt.so', 16 * 1024 * 1024)}
    hashes = {}
    for name, (path, cap) in files.items():
        facts = {}
        hashes[name] = _checked('HASH_' + name.removesuffix('_sha256').upper(),
                               lambda: _hash_file(path, cap, facts), facts)
    identity = {'idea_version': IDEA_VERSION, 'idea_build': IDEA_BUILD,
                'idea_archive_sha256': IDEA_ARCHIVE_SHA256, 'java_runtime_version': None,
                'hashes': hashes}
    return java, _checked('RUNTIME_SCHEMA', lambda: _runtime(identity))


def _authority(folder):
    def field(raw):
        return struct.pack('>H', len(raw)) + raw
    path = folder / 'authority'
    raw = (struct.pack('>H', 65535) + field(b'') + field(DISPLAY[1:].encode('ascii'))
           + field(b'MIT-MAGIC-COOKIE-1') + field(os.urandom(16)))
    with path.open('xb') as stream:
        stream.write(raw)
    path.chmod(0o600)
    return path


def _wait_xvfb(server, deadline):
    until = time.monotonic() + _remaining(deadline, 5)
    while time.monotonic() < until:
        require(server.poll() is None)
        if Path('/tmp/.X11-unix/X' + DISPLAY[1:]).exists():
            return
        time.sleep(.05)
    raise TimeoutError('XVFB_START')


def _ready(jvm, server, deadline):
    marker = ('AWT_TITLE_FIXTURE_READY:' + RUNTIME_VERSION + '\n').encode('ascii')
    require(jvm.stdout is not None)
    os.set_blocking(jvm.stdout.fileno(), False)
    received = b''
    until = time.monotonic() + _remaining(deadline, 20)
    while time.monotonic() < until:
        require(jvm.poll() is None and server.poll() is None)
        available, _, _ = select.select([jvm.stdout], [], [], min(.1, _remaining(until, .1)))
        if available:
            chunk = os.read(jvm.stdout.fileno(), len(marker) + 1 - len(received))
            require(bool(chunk))
            received += chunk
            require(len(received) <= len(marker) and marker.startswith(received))
            if received == marker:
                return
    raise TimeoutError('JVM_READY')


def _reap(process, pidfd):
    """Only the exact, unreaped Popen child; never groups or discovered PIDs."""
    if process is None:
        return 'NOT_STARTED'
    try:
        if process.poll() is None:
            try:
                if pidfd is not None:
                    signal.pidfd_send_signal(pidfd, signal.SIGTERM)
                else:
                    process.terminate()
            except ProcessLookupError:
                pass  # The child may exit between poll and the exact-child signal.
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            try:
                if pidfd is not None:
                    signal.pidfd_send_signal(pidfd, signal.SIGKILL)
                else:
                    process.kill()
            except ProcessLookupError:
                pass
            process.wait(timeout=2)
        require(process.returncode is not None)
        return 'REAPED'
    except BaseException:
        return 'UNVERIFIED'
    finally:
        for stream in (process.stdin, process.stdout, process.stderr):
            if stream is not None:
                try:
                    stream.close()
                except OSError:
                    pass


def _probe_document(value):
    _closed(value, ('schema', 'status', 'cases', 'diagnosis'))
    require(type(value['schema']) is int and value['schema'] == 1)
    require(type(value['status']) is str and value['status'] in ('PASS', 'FAIL'))
    cases = _cases(value['cases'])
    diagnosis = None if value['diagnosis'] is None else modal_window.failure_document(value['diagnosis'])
    require((value['status'] == 'PASS' and len(cases) == len(CASE_NAMES) and diagnosis is None)
            or (value['status'] == 'FAIL' and diagnosis is not None))
    return {**value, 'cases': cases, 'diagnosis': diagnosis}


def _legacy_encoding(x, window):
    """Zero-length metadata read only, after the production selector accepts WM_NAME."""
    atom = x.x.XInternAtom(x.connection, b'WM_NAME', True)
    x.sync()
    require(bool(atom))
    actual, fmt = C.c_ulong(), C.c_int()
    count, remaining, data = C.c_ulong(), C.c_ulong(), C.c_void_p()
    try:
        code = x.x.XGetWindowProperty(x.connection, window, atom, 0, 0, False, 0,
                                     C.byref(actual), C.byref(fmt), C.byref(count),
                                     C.byref(remaining), C.byref(data))
        x.sync()
        require(code == 0 and fmt.value == 8 and count.value == 0
                and 0 < remaining.value <= modal_window.MAX_TITLE_BYTES)
        atoms = x._title_type_atoms()
        encoding = next((name for name in (b'STRING', b'UTF8_STRING', b'COMPOUND_TEXT')
                         if atoms[name] != 0 and atoms[name] == actual.value), None)
        require(encoding is not None)
        return encoding.decode('ascii')
    finally:
        if data:
            x.x.XFree(data)


def _probe(jvm_pid):
    """All reads/writes occur inside a separately killed-and-reaped two-second probe."""
    require(type(jvm_pid) is int and 1 < jvm_pid <= 2 ** 31 - 1)
    require(os.environ.get('DISPLAY') == DISPLAY)
    result = {'schema': 1, 'status': 'FAIL', 'cases': [], 'diagnosis': None}
    deadline = time.monotonic() + PROBE_SECONDS
    try:
        with modal_window._X11(DISPLAY, deadline) as x:
            root = x.root()
            windows = {}
            until = time.monotonic() + min(1.25, _remaining(deadline, 1.25))
            while time.monotonic() < until:
                windows = {}
                for window in x.tree(root, modal_window.MAX_ROOT_CHILDREN)[2]:
                    # Ignore all non-child windows before reading their title.
                    if x.property(window, b'_NET_WM_PID', 32, b'CARDINAL') != jvm_pid:
                        continue
                    attrs = x.attributes(window, root)
                    title = attrs['title_sha256']
                    if title in MODERN_HASHES:
                        require(title not in windows and attrs['pid'] == jvm_pid
                                and attrs['map_state'] == 2 and attrs['window_class'] == 1)
                        windows[title] = window
                if len(windows) == 2:
                    break
                time.sleep(.025)
            require(len(windows) == 2)
            for index, digest in enumerate(MODERN_HASHES):
                require(x.title(windows[digest]) == digest)
                result['cases'].append({'case': CASE_NAMES[index], 'status': 'PASS',
                                        'title_sha256': digest, 'title_encoding': 'UTF8_STRING'})
            # Only this fixture introduces writes; the production _X11 stays read-only.
            ptr, u, i = C.c_void_p, C.c_ulong, C.c_int
            specs = {'XDeleteProperty': ([ptr, u, u], i),
                     'XCreateSimpleWindow': ([ptr, u, i, i, C.c_uint, C.c_uint, C.c_uint, u, u], u),
                     'XChangeProperty': ([ptr, u, u, u, i, i, ptr, i], i),
                     'XDestroyWindow': ([ptr, u], i)}
            for name, (args, output) in specs.items():
                fn = getattr(x.x, name)
                fn.argtypes, fn.restype = args, output
            modern = x.x.XInternAtom(x.connection, b'_NET_WM_NAME', True)
            x.sync()
            require(bool(modern))
            for index, digest in enumerate(MODERN_HASHES):
                window = windows[digest]
                require(x.property(window, b'_NET_WM_PID', 32, b'CARDINAL') == jvm_pid
                        and x.title(window) == digest)
                x.x.XDeleteProperty(x.connection, window, modern)
                x.sync()
                legacy = x.title(window)
                require(legacy is not None and legacy != digest)
                encoding = _legacy_encoding(x, window)
                require(x.title(window) == legacy)
                result['cases'].append({'case': CASE_NAMES[index + 2], 'status': 'PASS',
                                        'title_sha256': legacy, 'title_encoding': encoding})
            synthetic = x.x.XCreateSimpleWindow(x.connection, root, 0, 0, 1, 1, 0, 0, 0)
            x.sync()
            require(bool(synthetic))
            try:
                string = x.x.XInternAtom(x.connection, b'STRING', False)
                raw = C.create_string_buffer(b'owned fixture')
                x.x.XChangeProperty(x.connection, synthetic, modern, string, 8, 0, C.cast(raw, ptr), 13)
                x.sync()
                try:
                    x.title(synthetic)
                except modal_window.ProofError as error:
                    require(error.call_site == 'X_PROPERTY_TYPE'
                            and error.facts.get('property_name') == 2
                            and error.facts.get('actual_type') == 1
                            and error.facts.get('type_matches') == 0)
                    result['cases'].append({'case': CASE_NAMES[4], 'status': 'REJECTED',
                                            'title_sha256': None, 'title_encoding': None})
                else:
                    raise ValueError('WRONG_TYPE_ACCEPTED')
            finally:
                x.x.XDestroyWindow(x.connection, synthetic)
                x.sync()
            result['status'] = 'PASS'
    except Exception as error:
        result['status'] = 'FAIL'
        result['diagnosis'] = modal_window.failure_from_exception(error)
    return _probe_document(result)


def main(toolchain_root, output):
    start = time.monotonic()
    deadline = start + ACTIVITY_SECONDS
    report = {'schema': 1, 'status': 'FAIL', 'kind': KIND, 'cases': [],
              'cleanup': {'jvm': 'NOT_STARTED', 'xvfb': 'NOT_STARTED'},
              'exit_codes': {'jvm': None, 'xvfb': None},
              'error': 'PRECHECK_UNAVAILABLE', 'diagnosis': None, 'runtime': None, 'precheck_failure': None,
              'run_id': os.environ['GITHUB_RUN_ID'], 'run_attempt': os.environ['GITHUB_RUN_ATTEMPT'],
              'tested_sha': os.environ['GITHUB_SHA'], 'elapsed_milliseconds': 0}
    # Reject malformed current-source/run identity before entering any precheck.
    for key, pattern in (('run_id', r'[1-9][0-9]{0,19}'), ('run_attempt', r'[1-9][0-9]{0,19}'),
                         ('tested_sha', r'[0-9a-f]{40}')):
        _token(report[key], pattern)
    server = jvm = None
    server_fd = jvm_fd = None
    temporary = None
    def stop(signum, _frame):
        if signum == signal.SIGALRM:
            raise TimeoutError('FIXTURE_BUDGET')
        raise InterruptedError('FIXTURE_CANCELLED')
    saved = {sig: signal.getsignal(sig) for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGALRM)}
    for sig in saved:
        signal.signal(sig, stop)
    signal.alarm(ACTIVITY_SECONDS)
    try:
        java, report['runtime'] = _runtime_identity(toolchain_root)
        _checked('PIDFD_CAPABILITY', lambda: require(hasattr(os, 'pidfd_open') and hasattr(signal, 'pidfd_send_signal')))
        _checked('XVFB_BINARY', lambda: require(BINARY.is_file() and not BINARY.is_symlink()))
        _checked('DISPLAY_AVAILABLE', lambda: require(not Path('/tmp/.X11-unix/X' + DISPLAY[1:]).exists()
                and not Path('/tmp/.X' + DISPLAY[1:] + '-lock').exists()))
        temporary = _checked('PRIVATE_DIRECTORY', lambda: tempfile.TemporaryDirectory(prefix='academy-awt-title-'))
        folder = Path(temporary.name)
        _checked('PRIVATE_DIRECTORY', lambda: folder.chmod(0o700))
        authority = _checked('AUTHORITY_CREATE', lambda: _authority(folder))
        env = {'PATH': os.defpath, 'LANG': 'C.UTF-8', 'DISPLAY': DISPLAY,
               'XAUTHORITY': str(authority), 'HOME': str(folder), 'TMPDIR': str(folder),
               'XDG_CACHE_HOME': str(folder / 'cache')}
        report['error'] = 'XVFB_START_UNAVAILABLE'
        server = subprocess.Popen([str(BINARY), DISPLAY, '-screen', '0', '1280x900x24',
                                   '-nolisten', 'tcp', '-auth', str(authority), '-noreset'],
                                  env=env, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                  stderr=subprocess.DEVNULL, start_new_session=True)
        server_fd = os.pidfd_open(server.pid)
        _wait_xvfb(server, deadline)
        report['error'] = 'JVM_START_UNAVAILABLE'
        jvm = subprocess.Popen([str(java), '-Xmx64m', '-XX:ActiveProcessorCount=2',
                                '-Djava.awt.headless=false', '--source', '25', str(HELPER)],
                               env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                               stderr=subprocess.DEVNULL, start_new_session=True)
        jvm_fd = os.pidfd_open(jvm.pid)
        _ready(jvm, server, deadline)
        report['runtime']['java_runtime_version'] = RUNTIME_VERSION
        report['error'] = 'JVM_EXITED'
        require(jvm.poll() is None and server.poll() is None)
        report['error'] = 'PROBE_FAILED'
        try:
            probed = subprocess.run([sys.executable, '-B', str(Path(__file__).resolve()), '--probe', str(jvm.pid)],
                                    env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                    stderr=subprocess.DEVNULL, timeout=_remaining(deadline, PROBE_SECONDS))
        except subprocess.TimeoutExpired:
            report['error'] = 'PROBE_TIMEOUT'
            raise
        require(len(probed.stdout) <= 8192)
        result = _probe_document(json_read(probed.stdout))
        report['cases'], report['diagnosis'] = result['cases'], result['diagnosis']
        require(probed.returncode == 0 and result['status'] == 'PASS')
        report['error'] = 'JVM_EXITED'
        require(jvm.poll() is None and server.poll() is None)
        _remaining(deadline, 1)
        report['status'], report['error'] = 'PASS', None
    except BaseException as error:
        report['status'] = 'FAIL'
        if isinstance(error, PrecheckFailure):
            report['precheck_failure'] = error.document
            error = error.__cause__
        if isinstance(error, InterruptedError) or isinstance(error, KeyboardInterrupt):
            report['error'] = 'CANCELLED'
        elif isinstance(error, TimeoutError) and time.monotonic() >= deadline:
            report['error'] = 'BUDGET_EXHAUSTED'
    finally:
        signal.alarm(0)
        # Preserve at most eight seconds for independent TERM/KILL/reap attempts.
        for sig in saved:
            signal.signal(sig, signal.SIG_IGN)
        report['cleanup']['jvm'] = _reap(jvm, jvm_fd)
        report['cleanup']['xvfb'] = _reap(server, server_fd)
        for child, process in (('jvm', jvm), ('xvfb', server)):
            code = None if process is None else process.returncode
            report['exit_codes'][child] = code if type(code) is int and -128 <= code <= 255 else None
        for fd in (jvm_fd, server_fd):
            if fd is not None:
                try:
                    os.close(fd)
                except OSError:
                    report.update(status='FAIL', error='CLEANUP_UNVERIFIED')
        if 'UNVERIFIED' in report['cleanup'].values():
            report.update(status='FAIL', error='CLEANUP_UNVERIFIED')
        if temporary is not None:
            try:
                temporary.cleanup()
            except OSError:
                report.update(status='FAIL', error='CLEANUP_UNVERIFIED')
        report['elapsed_milliseconds'] = max(0, int((time.monotonic() - start) * 1000))
        for sig, handler in saved.items():
            signal.signal(sig, handler)
        publish(output, encode(report_document(report)))
    if report['status'] != 'PASS':
        raise SystemExit(1)


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--toolchain-root', type=Path)
    parser.add_argument('--report', type=Path)
    parser.add_argument('--probe', type=int)
    args = parser.parse_args()
    if args.probe is not None:
        require(args.toolchain_root is None and args.report is None)
        result = _probe(args.probe)
        sys.stdout.buffer.write(encode(result))
        raise SystemExit(0 if result['status'] == 'PASS' else 1)
    require(args.toolchain_root is not None and args.report is not None)
    main(args.toolchain_root, args.report)
