"""One nonprivileged, closed descendant family; this module alone reaps its children.

No Popen object, process-name search, global PID scan, privilege change or vendor
modification. Kernel-adopted terminal children receive no signal/GUI authority.
"""
import ctypes
import hashlib
import os
from pathlib import Path
import select
import signal
import stat
import subprocess
import tempfile
import time

MAX_MEMBERS = 512  # Cumulative for preparation + restart + fresh validation.
MAX_TASKS = 1024
MAX_CHILD_BYTES = 65536


CODES = frozenset(('AUTOMATIC_REAPER_FORBIDDEN', 'CHILD_BIRTH_UNVERIFIED', 'CHILD_DISCOVERY_LIMIT', 'CHILD_GROUP_UNVERIFIED', 'CHILD_IDENTITY_UNVERIFIED', 'CHILD_METADATA_INVALID', 'CHILD_METADATA_LIMIT', 'CHILD_ROLE_INVALID', 'COMPETING_REAPER', 'CONCURRENT_REAPER', 'CUMULATIVE_PROCESS_LIMIT', 'DEADLINE_INVALID', 'DESCRIPTOR_LIMIT', 'EXECUTABLE_CHANGED', 'EXEC_FAILED', 'EXEC_HANDSHAKE_DEADLINE', 'EXEC_IDENTITY_CHANGED', 'FAMILY_CLEANUP_INCOMPLETE', 'FAST_CHILD_UNRECORDED', 'HELPER_OUTPUT_LIMIT', 'HELPER_STREAM_INVALID', 'INITIAL_CHILDREN_PRESENT', 'LIVE_CHILD_BLOCKS_VALIDATION', 'MULTIPLE_REPLACEMENT_IDES', 'MULTIPLE_RESTARTERS', 'NEW_LAUNCH_FORBIDDEN', 'NORMAL_CLOSE_NOT_AUTHORIZED', 'PID_REUSE_OR_DUPLICATE', 'PROCESS_METADATA_LIMIT', 'REGISTERED_IDENTITY_CHANGED', 'REPARENT_UNVERIFIED', 'REPLACEMENT_EXECUTABLE_INVALID', 'REPLACEMENT_IDENTITY_INVALID', 'RESTARER_BINARY_MISMATCH', 'RESTARER_COMMAND_MISMATCH', 'RESTART_ARM_INVALID', 'RESTART_CLICK_INVALID', 'RESTART_DEADLINE', 'RESTART_IMAGES_ALREADY_SET', 'RESTART_NOT_DISPATCHED', 'SUBREAPER_UNAVAILABLE', 'SUBREAPER_UNVERIFIED', 'SUPERVISOR_PARENT_UNVERIFIED', 'THREADED_SPAWN_FORBIDDEN', 'UNEXPECTED_PREPARATION_EXIT', 'UNEXPECTED_RESTARTED_EXIT', 'VALIDATION_TRANSITION_FORBIDDEN', 'WAIT_CHILD_IDENTITY_INVALID', 'WAIT_PID_IDENTITY_CHANGED'))
CODES |= frozenset(('EXPECTED_HELPER_INVALID', 'EXPECTED_HELPER_CHANGED', 'SUDO_PROBE_INVALID',
                    'INSTALL_HELPERS_INVALID', 'TERMINAL_IDENTITY_INVALID', 'MULTIPLE_INSTALL_TERMINALS',
                    'INSTALL_HELPERS_INCOMPLETE', 'INSTALL_HELPER_FAILED', 'TERMINAL_ACK_INVALID'))

class FamilyError(RuntimeError):
    def __init__(self, code):
        self.code = code if code in CODES else 'PROCESS_METADATA_LIMIT'
        super().__init__(self.code)


class Cancellation:
    def __init__(self):
        self.cancelled = False
        self.reason = None

    def set(self, reason='CANCELLED'):
        self.cancelled = True
        if self.reason is None:
            self.reason = reason

    def check(self):
        if self.cancelled:
            raise InterruptedError(self.reason)


def info(pid):
    root = Path('/proc') / str(pid)
    raw = (root / 'stat').read_bytes()
    if len(raw) > 16384:
        raise FamilyError('PROCESS_METADATA_LIMIT')
    fields = raw.rsplit(b')', 1)[1].split()
    return {'pid': pid, 'ppid': int(fields[1]), 'pgrp': int(fields[2]),
            'session': int(fields[3]), 'start_time': fields[19].decode('ascii'),
            'uid': root.stat().st_uid, 'state': fields[0].decode('ascii')}


def stable(meta):
    return {key: meta[key] for key in ('pid', 'start_time', 'uid')}


def birth(meta):
    """A held pidfd anchors birth even when an expected helper changes UID."""
    return (meta['pid'], meta['start_time'])


def file_identity(value):
    return [value.st_dev, value.st_ino, value.st_uid, value.st_mode,
            value.st_size, value.st_mtime_ns, value.st_ctime_ns]


def alive(fd):
    return not select.select([fd], [], [], 0)[0]


def children(meta, deadline):
    values = set()
    count = 0
    for task in (Path('/proc') / str(meta['pid']) / 'task').iterdir():
        count += 1
        if count > MAX_TASKS or time.monotonic() >= deadline:
            raise FamilyError('CHILD_DISCOVERY_LIMIT')
        try:
            with (task / 'children').open('rb') as stream:
                raw = stream.read(MAX_CHILD_BYTES + 1)
        except FileNotFoundError:
            continue
        if len(raw) > MAX_CHILD_BYTES:
            raise FamilyError('CHILD_METADATA_LIMIT')
        for word in raw.split():
            if not word.isdigit() or len(word) > 10:
                raise FamilyError('CHILD_METADATA_INVALID')
            pid = int(word)
            if not 0 < pid < 2**31:
                raise FamilyError('CHILD_METADATA_INVALID')
            values.add(pid)
        if len(values) > MAX_MEMBERS:
            raise FamilyError('CHILD_DISCOVERY_LIMIT')
    return values


class Child:
    """Compatibility facade: poll reads only this family's terminal ledger."""
    def __init__(self, family, key):
        self.family = family
        self.key = key
        self.pid = key[0]

    @property
    def returncode(self):
        return self.family.members[self.key]['exit_code']

    def poll(self):
        self.family.tick()
        return self.returncode


class Family:
    def __init__(self, deadline, cancellation=None):
        if type(deadline) not in (int, float) or not time.monotonic() < deadline <= time.monotonic() + 2700:
            raise FamilyError('DEADLINE_INVALID')
        self.deadline = deadline
        self.cancel = cancellation or Cancellation()
        self.owner = info(os.getpid())
        self.parent = info(os.getppid())
        self.parent_fd = os.pidfd_open(self.parent['pid'])
        if not alive(self.parent_fd) or info(self.parent['pid']) != self.parent:
            os.close(self.parent_fd)
            raise FamilyError('SUPERVISOR_PARENT_UNVERIFIED')
        self.members = {}
        self.pid_keys = {}
        self.launches_closed = False
        self.phase_closed = False
        self.closed = False
        self.last_echild = False
        self.restart = None
        self.tick_active = False
        self.cleanup_active = False
        self.cleanup_deadline = None
        self.pending_launch = False
        self.normal_close_key = None
        self.restart_images = None
        self.sudo_probe = None
        self.pending_helper = None
        self.pending_pid = None
        self.pending_role = None
        self.install_helpers = None
        self.install_old_key = None
        self.terminal_key = None
        self.terminal_verified_key = None
        self.observation_failed = False
        if signal.getsignal(signal.SIGCHLD) != signal.SIG_DFL:
            raise FamilyError('AUTOMATIC_REAPER_FORBIDDEN')
        try:
            os.waitid(os.P_ALL, 0, os.WEXITED | os.WNOHANG | os.WNOWAIT)
        except ChildProcessError:
            pass
        else:
            raise FamilyError('INITIAL_CHILDREN_PRESENT')
        libc = ctypes.CDLL(None, use_errno=True)
        libc.prctl.argtypes = [ctypes.c_int, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_ulong]
        libc.prctl.restype = ctypes.c_int
        if libc.prctl(36, 1, 0, 0, 0) != 0:  # PR_SET_CHILD_SUBREAPER
            raise FamilyError('SUBREAPER_UNAVAILABLE')
        result = ctypes.c_int()
        if libc.prctl(37, ctypes.addressof(result), 0, 0, 0) != 0 or result.value != 1:
            raise FamilyError('SUBREAPER_UNVERIFIED')

    def check(self):
        self.cancel.check()
        if self.closed or time.monotonic() >= self.deadline:
            self.cancel.set('DEADLINE_OR_CLOSED')
            self.cancel.check()
        try:
            same = alive(self.parent_fd) and stable(info(self.owner['pid'])) == stable(self.owner) and stable(info(self.parent['pid'])) == stable(self.parent)
        except (FileNotFoundError, ProcessLookupError):
            same = False
        if not same:
            self.cancel.set('SUPERVISOR_PARENT_LOST')
            self.cancel.check()

    def _reserve(self):
        if len(self.members) >= MAX_MEMBERS:
            raise FamilyError('CUMULATIVE_PROCESS_LIMIT')

    def _expected_binary(self, record):
        from safe_io import read_regular
        if (type(record) is not dict or set(record) != {'path', 'identity', 'sha256'}
                or type(record['path']) is not str or not Path(record['path']).is_absolute()
                or type(record['identity']) is not list or len(record['identity']) != 7
                or any(type(value) is not int for value in record['identity'])
                or type(record['sha256']) is not str or len(record['sha256']) != 64
                or any(value not in '0123456789abcdef' for value in record['sha256'])):
            raise FamilyError('EXPECTED_HELPER_INVALID')
        path = Path(record['path'])
        before = path.lstat()
        if (not stat.S_ISREG(before.st_mode) or not before.st_mode & 0o111
                or file_identity(before) != record['identity']):
            raise FamilyError('EXPECTED_HELPER_CHANGED')
        raw = read_regular(path, limit=16*1024*1024)
        if hashlib.sha256(raw).hexdigest() != record['sha256'] or file_identity(path.lstat()) != record['identity']:
            raise FamilyError('EXPECTED_HELPER_CHANGED')
        return {'path': record['path'], 'identity': list(record['identity']), 'sha256': record['sha256']}

    def expect_sudo_probe(self, helper_identity):
        self.check()
        if self.sudo_probe is not None or self.pending_launch or self.launches_closed:
            raise FamilyError('SUDO_PROBE_INVALID')
        self.sudo_probe = self._expected_binary(helper_identity)

    def configure_install_helpers(self, expected_helpers, old_child):
        self.check(); self.tick()
        if (self.install_helpers is not None or self.restart is not None
                or type(expected_helpers) is not dict or set(expected_helpers) != {'TERMINAL', 'SUDO'}
                or old_child.family is not self or old_child.key not in self.members
                or self.members[old_child.key]['role'] != 'PREPARATION_IDE'
                or self.members[old_child.key]['terminal']):
            raise FamilyError('INSTALL_HELPERS_INVALID')
        verified = {kind: self._expected_binary(record) for kind, record in expected_helpers.items()}
        if verified['TERMINAL']['path'] == verified['SUDO']['path']:
            raise FamilyError('INSTALL_HELPERS_INVALID')
        self.install_helpers = verified
        self.install_old_key = old_child.key

    def _matches_binary(self, meta, expected):
        proc_exe = '/proc/' + str(meta['pid']) + '/exe'
        if os.readlink(proc_exe) != expected['path']:
            return False
        if (file_identity(Path(expected['path']).lstat()) != expected['identity']
                or file_identity(os.stat(proc_exe)) != expected['identity']):
            raise FamilyError('EXPECTED_HELPER_CHANGED')
        return True

    def _terminal_branch_proved(self, parent):
        """An exact live terminal anchors lifecycle-only elevated descendants."""
        if sum(item.get('helper_kind') == 'TERMINAL' for item in self.members.values()) != 1:
            raise FamilyError('MULTIPLE_INSTALL_TERMINALS')
        root = self.members.get(parent.get('terminal_root'))
        if (root is None or root.get('helper_kind') != 'TERMINAL' or root.get('lifecycle_only')
                or root['terminal'] or root['fd'] is None or not alive(root['fd'])
                or root.get('lineage') != self.install_old_key or not self._born_after_arm(root)):
            raise FamilyError('TERMINAL_IDENTITY_INVALID')
        before = info(root['meta']['pid'])
        if (stable(before) != stable(root['meta']) or before['uid'] != self.owner['uid']
                or not self._matches_binary(before, self.install_helpers['TERMINAL'])
                or not alive(root['fd']) or stable(info(before['pid'])) != stable(before)):
            raise FamilyError('TERMINAL_IDENTITY_INVALID')

    def _helper_kind(self, meta, parent):
        # The fork/exec handshake supplies the exact one-shot probe command.
        # This also covers a child observed before exec or already terminal.
        if meta['pid'] == self.pending_pid and self.pending_helper is not None:
            return 'SUDO_PROBE'
        if parent is not None and meta['ppid'] != parent['meta']['pid']:
            raise FamilyError('CHILD_IDENTITY_UNVERIFIED')
        if parent is not None and parent.get('lifecycle_only'):
            return 'ELEVATED_DESCENDANT'
        if self.install_helpers is None or self.restart is None:
            return None
        if parent is None:
            return None  # No invented terminal/sudo ancestry for adopted strangers.
        if parent.get('terminal_root') is not None:
            if meta['uid'] != self.owner['uid']:
                self._terminal_branch_proved(parent)
                # Setuid/dumpability can hide this descendant's executable.
                # Proven terminal ancestry grants observation only; this does
                # not assert a sudo image or authorize GUI actions/signals.
                return 'TERMINAL_ELEVATED_DESCENDANT'
            if self._matches_binary(meta, self.install_helpers['SUDO']):
                return 'SUDO'
            return 'TERMINAL_DESCENDANT'
        if (parent['key'] == self.install_old_key or parent.get('lineage') == self.install_old_key):
            if self._matches_binary(meta, self.install_helpers['TERMINAL']):
                return 'TERMINAL'
        return None

    def _set_helper(self, item, kind, parent=None):
        item['helper_kind'] = kind
        item['lifecycle_only'] = kind in ('SUDO_PROBE', 'SUDO', 'ELEVATED_DESCENDANT', 'TERMINAL_ELEVATED_DESCENDANT')
        item['helper_image_observed'] = kind in ('TERMINAL', 'SUDO')
        item['never_signal'] = item.get('never_signal', False) or item['lifecycle_only']
        item['helper_lineage'] = item.get('helper_lineage', False) or kind is not None or bool(parent and parent.get('helper_lineage'))
        item['terminal_root'] = (item['key'] if kind == 'TERMINAL'
                                 else parent.get('terminal_root') if parent else None)
        if kind is not None:
            item['role'] = 'INSTALL_TERMINAL' if kind == 'TERMINAL' else 'EXPECTED_HELPER'

    def _refresh(self, item, current, error='REGISTERED_IDENTITY_CHANGED'):
        if (birth(current) != birth(item['meta'])
                or (current['uid'] != item['meta']['uid'] and not item.get('lifecycle_only'))):
            raise FamilyError(error)
        if current['ppid'] != item['meta']['ppid']:
            old = self.members.get(self.pid_keys.get(item['meta']['ppid']))
            if (current['ppid'] != self.owner['pid'] or old is None
                    or (old['fd'] is not None and alive(old['fd']))):
                raise FamilyError('REPARENT_UNVERIFIED')
            item['adopted'] = True
        if current['uid'] not in item['observed_uids']:
            if len(item['observed_uids']) >= 16:
                raise FamilyError('PROCESS_METADATA_LIMIT')
            item['observed_uids'].append(current['uid'])
        item['meta'] = current

    def _record_live(self, pid, provenance, parent=None):
        self._reserve()
        before = info(pid)
        if before['state'] in ('Z', 'X'):
            return None  # Only waitid(WNOWAIT), never a live registry, admits zombies.
        expected_parent = self.owner if parent is None else parent['meta']
        if before['ppid'] != expected_parent['pid']:
            raise FamilyError('CHILD_IDENTITY_UNVERIFIED')
        if int(before['start_time']) < int(expected_parent['start_time']):
            raise FamilyError('CHILD_BIRTH_UNVERIFIED')
        sessions = {expected_parent['session'], pid}
        groups = {expected_parent['pgrp'], pid}
        if provenance == 'KERNEL_SUBREAPER_CHILD':
            sessions.update(item['meta']['session'] for item in self.members.values())
            groups.update(item['meta']['pgrp'] for item in self.members.values())
        if before['session'] not in sessions or before['pgrp'] not in groups:
            raise FamilyError('CHILD_GROUP_UNVERIFIED')
        fd = os.pidfd_open(pid)
        try:
            if not alive(fd):
                return None
            kind = self._helper_kind(before, parent)
            lifecycle_only = kind in ('SUDO_PROBE', 'SUDO', 'ELEVATED_DESCENDANT', 'TERMINAL_ELEVATED_DESCENDANT')
            if before['uid'] != self.owner['uid'] and not lifecycle_only:
                raise FamilyError('CHILD_IDENTITY_UNVERIFIED')
            after = info(pid)
            if (birth(after) != birth(before) or any(after[key] != before[key] for key in ('ppid', 'pgrp', 'session'))
                    or (after['uid'] != before['uid'] and not lifecycle_only)):
                raise FamilyError('CHILD_IDENTITY_UNVERIFIED')
            if not alive(fd):
                return None
            if parent is not None:
                if not alive(parent['fd']):
                    return None
                self._refresh(parent, info(expected_parent['pid']))
            key = (pid, before['start_time'])
            if pid in self.pid_keys:
                old = self.members[self.pid_keys[pid]]
                if old['key'] != key or not old['terminal']:
                    raise FamilyError('PID_REUSE_OR_DUPLICATE')
                return key
            item = {'key': key, 'meta': after, 'birth_meta': before, 'fd': fd, 'provenance': provenance,
                                 'terminal': False, 'reaped': False, 'exit_code': None, 'role': 'DESCENDANT',
                                 'terminal_evidence': None, 'observed_uids': [before['uid']],
                                 'adopted': parent is None and pid != self.pending_pid,
                                 'lineage': parent.get('lineage') if parent else None}
            if after['uid'] != before['uid']:
                item['observed_uids'].append(after['uid'])
            self._set_helper(item, kind, parent)
            if pid == self.pending_pid:
                item['provenance'] = 'DIRECT_SPAWN'
                item['lineage'] = key
                item['helper_lineage'] = self.pending_role == 'HELPER'
                if kind is None:
                    item['role'] = self.pending_role
            self.members[key] = item
            self.pid_keys[pid] = key
            fd = None
            return key
        finally:
            if fd is not None:
                os.close(fd)

    def spawn(self, command, environment, *, role, stdin_fd=None, stdout_fd=None, stderr_fd=None, pass_fds=(), _expected_helper=None):
        self.check()
        if self.launches_closed or self.phase_closed or self.pending_launch:
            raise FamilyError('NEW_LAUNCH_FORBIDDEN')
        self._reserve()
        if role not in ('PREPARATION_IDE', 'VALIDATION_IDE', 'HELPER'):
            raise FamilyError('CHILD_ROLE_INVALID')
        # A single-thread fork/exec works even when Python was built without
        # POSIX_SPAWN_SETSID. No Popen finalizer or poll may reap the child.
        if len(list(Path('/proc/self/task').iterdir())) != 1:
            raise FamilyError('THREADED_SPAWN_FORBIDDEN')
        read_fd, write_fd = os.pipe2(os.O_CLOEXEC | os.O_NONBLOCK)
        descriptors = [int(p.name) for p in Path('/proc/self/fd').iterdir() if p.name.isdigit()]
        if len(descriptors) > 2048:
            os.close(read_fd); os.close(write_fd)
            raise FamilyError('DESCRIPTOR_LIMIT')
        try:
            pid = os.fork()
        except BaseException:
            os.close(read_fd);os.close(write_fd)
            self.cancel.set('SPAWN_REGISTRATION_FAILED')
            raise
        if pid == 0:
            try:
                os.setsid()
                for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGCHLD):
                    signal.signal(sig, signal.SIG_DFL)
                for target, source in ((0, stdin_fd), (1, stdout_fd), (2, stderr_fd)):
                    if source is not None:
                        os.dup2(source, target)
                for fd in pass_fds:
                    os.set_inheritable(fd, True)
                keep = {0, 1, 2, write_fd, *pass_fds}
                for fd in descriptors:
                    if fd not in keep:
                        try: os.close(fd)
                        except OSError: pass  # /proc iterator's own FD already closed.
                os.execve(command[0], command, environment)
            except BaseException:
                try: os.write(write_fd, b'E')
                except OSError: pass
                os._exit(127)
        os.close(write_fd)
        self.pending_launch = True
        self.pending_pid = pid
        self.pending_helper = _expected_helper
        self.pending_role = role
        try:
            end = min(self.deadline, time.monotonic() + 3)
            while True:
                self.check()
                if time.monotonic() >= end:
                    raise FamilyError('EXEC_HANDSHAKE_DEADLINE')
                if select.select([read_fd], [], [], .01)[0]:
                    if os.read(read_fd, 2):
                        raise FamilyError('EXEC_FAILED')
                    break  # CLOEXEC EOF; child established its new session.
                self.tick()
            key = self.pid_keys.get(pid)
            if key is None:
                key = self._record_live(pid, 'DIRECT_SPAWN')
            if key is None:
                self._reap()
                key = self.pid_keys.get(pid)
                if key is None:
                    raise FamilyError('FAST_CHILD_UNRECORDED')
            item = self.members[key]
            item['spawn_role'] = role
            if not item['terminal']:
                # The parent selected the exact preverified one-shot command;
                # successful CLOEXEC EOF proves this fork's exec completed.
                # A setuid executable can make /proc/PID/exe inaccessible, so
                # do not require a duplicate image observation for this route.
                item['role'] = 'EXPECTED_HELPER' if _expected_helper is not None else role
                item['provenance'] = 'DIRECT_SPAWN'
                item['lineage'] = key
                item['adopted'] = False
                item['helper_lineage'] = role == 'HELPER'
            return Child(self, key)
        except BaseException:
            self.cancel.set('SPAWN_REGISTRATION_FAILED')
            raise
        finally:
            self.pending_launch = False
            self.pending_pid = None
            self.pending_helper = None
            self.pending_role = None
            os.close(read_fd)

    def run(self, command, *, env=None, stdout=None, stderr=None, timeout=None, check=False, pass_fds=()):
        """Bounded helper adapter; every child remains in the single exit ledger."""
        self.check()
        end = min(self.deadline, time.monotonic() + (timeout if timeout is not None else 15))
        files = []
        try:
            expected = self.sudo_probe
            self.sudo_probe = None  # One shot, including an invalid attempted command.
            if expected is not None and list(command) != [expected['path'], '-n', '-l']:
                raise FamilyError('SUDO_PROBE_INVALID')
            if expected is not None:
                self._expected_binary(expected)
            def output(value):
                if value == subprocess.PIPE:
                    stream = tempfile.TemporaryFile(); files.append(stream); return stream
                if value == subprocess.DEVNULL:
                    stream = open('/dev/null', 'wb'); files.append(stream); return stream
                if value is None:
                    return None
                raise FamilyError('HELPER_STREAM_INVALID')
            out = output(stdout); err = output(stderr)
            child = self.spawn(command, env or {}, role='HELPER',
                               stdout_fd=out.fileno() if out else None,
                               stderr_fd=err.fileno() if err else None, pass_fds=pass_fds,
                               _expected_helper=expected)
            while child.poll() is None:
                if time.monotonic() >= end:
                    raise subprocess.TimeoutExpired(command[0], timeout)
                if any(os.fstat(stream.fileno()).st_size > 256*1024 for stream in (out,err) if stream):
                    raise FamilyError('HELPER_OUTPUT_LIMIT')
                time.sleep(.01)
            def captured(stream, requested):
                if requested != subprocess.PIPE:
                    return None
                stream.seek(0); raw=stream.read(256*1024+1)
                if len(raw)>256*1024:
                    raise FamilyError('HELPER_OUTPUT_LIMIT')
                return raw
            result = subprocess.CompletedProcess([command[0]], child.returncode,
                                                  captured(out,stdout), captured(err,stderr))
            if check and result.returncode:
                raise subprocess.CalledProcessError(result.returncode, command[0])
            self.check()
            return result
        except BaseException:
            self.cancel.set('HELPER_FAILED')
            raise
        finally:
            for stream in files:
                stream.close()

    def _reap(self):
        """The sole wait authority; terminal unknown children cannot become GUI candidates."""
        self.last_echild = False
        while True:
            try:
                observed = os.waitid(os.P_ALL, 0, os.WEXITED | os.WNOHANG | os.WNOWAIT)
            except ChildProcessError:
                self.last_echild = True
                return
            if observed is None:
                return  # A surviving child exists; /proc discovery may have missed it.
            pid = observed.si_pid
            key = self.pid_keys.get(pid)
            meta = info(pid)
            if meta['ppid'] != self.owner['pid'] or meta['state'] not in ('Z', 'X'):
                raise FamilyError('WAIT_CHILD_IDENTITY_INVALID')
            if key is None:
                self._reserve()
                key = (pid, meta['start_time'])
                kind = 'SUDO_PROBE' if pid == self.pending_pid and self.pending_helper is not None else None
                if meta['uid'] != self.owner['uid'] and kind is None:
                    raise FamilyError('WAIT_CHILD_IDENTITY_INVALID')
                item = {'key': key, 'meta': meta, 'birth_meta': meta, 'fd': None,
                                     'provenance': 'TERMINAL_KERNEL_CHILD', 'terminal': True,
                                     'reaped': False, 'exit_code': None, 'role': 'TERMINAL_ONLY', 'lineage': None,
                                     'adopted': False, 'observed_uids': [meta['uid']], 'terminal_evidence': None}
                self._set_helper(item, kind)
                self.members[key] = item
                self.pid_keys[pid] = key
            item = self.members[key]
            self._refresh(item, meta, 'WAIT_PID_IDENTITY_CHANGED')
            final = os.waitid(os.P_PID, pid, os.WEXITED | os.WNOHANG)
            if final is None or (final.si_pid, final.si_code, final.si_status) != (observed.si_pid, observed.si_code, observed.si_status):
                raise FamilyError('COMPETING_REAPER')
            item['terminal'] = True
            item['reaped'] = True
            item['terminal_evidence'] = 'WAITID_EXIT'
            item['wait_uid'] = final.si_uid
            item['exit_code'] = final.si_status if final.si_code == os.CLD_EXITED else -final.si_status

    def _discover(self):
        queue = [(self.owner, None)]
        seen = set()
        while queue:
            parent_meta, parent = queue.pop(0)
            if parent_meta['pid'] in seen:
                continue
            seen.add(parent_meta['pid'])
            if parent is not None and not alive(parent['fd']):
                continue
            try:
                limit = self.cleanup_deadline if self.cleanup_active else self.deadline
                candidates = children(parent_meta, min(limit, time.monotonic() + 1))
            except (FileNotFoundError, ProcessLookupError):
                continue
            for pid in candidates:
                key = self.pid_keys.get(pid)
                if key is None:
                    try:
                        key = self._record_live(pid, 'KERNEL_SUBREAPER_CHILD' if parent is None else 'VERIFIED_PARENT_CHILD', parent)
                    except (FileNotFoundError, ProcessLookupError):
                        continue
                if key is None:
                    continue
                item = self.members[key]
                if item['fd'] is not None and alive(item['fd']):
                    try:current = info(pid)
                    except (FileNotFoundError,ProcessLookupError):
                        if not alive(item['fd']):continue
                        raise FamilyError('REGISTERED_IDENTITY_CHANGED')
                    # A fork can be sampled before it execs terminal or sudo.
                    # Promote only after the exact expected executable is proved.
                    if not item.get('lifecycle_only') and item.get('helper_kind') != 'TERMINAL':
                        kind = self._helper_kind(current, parent)
                        if kind is not None:
                            self._set_helper(item, kind, parent)
                    self._refresh(item, current)
                    queue.append((current, item))

    def tick(self):
        if self.tick_active:
            raise FamilyError('CONCURRENT_REAPER')
        if not self.cleanup_active:
            self.check()
        self.tick_active = True
        try:
            self._reap()
            self._discover()
            self._reap()
            for item in self.members.values():
                if item['fd'] is not None and not alive(item['fd']):
                    if item['provenance'] == 'DIRECT_SPAWN' and not item['reaped']:
                        raise FamilyError('COMPETING_REAPER')
                    item['terminal'] = True
                    if not item['reaped']:
                        # A living registered parent may have consumed this exit.
                        # The held pidfd proves terminal state, not an exit code.
                        item['terminal_evidence'] = 'PIDFD_TERMINAL_STATUS_UNKNOWN'
                if item['terminal'] and item['role'] == 'PREPARATION_IDE':
                    if self.restart is None or self.restart['old_key'] != item['key']:
                        if not self.cleanup_active:
                            raise FamilyError('UNEXPECTED_PREPARATION_EXIT')
                if item['terminal'] and item['role'] == 'RESTARTED_IDE' and self.normal_close_key != item['key']:
                        if not self.cleanup_active:
                            raise FamilyError('UNEXPECTED_RESTARTED_EXIT')
            if self.restart is not None and self.restart_images is not None and not self.cleanup_active:
                self._observe_restart()
        except BaseException:
            self.observation_failed = True
            self.cancel.set('FAMILY_OBSERVATION_FAILED')
            raise
        finally:
            self.tick_active = False

    def scan(self):
        return self.tick()

    def arm_restart(self, child, binding):
        self.check()
        self.tick()
        if self.restart is not None or child.poll() is not None or type(binding) is not str or len(binding) != 64:
            raise FamilyError('RESTART_ARM_INVALID')
        self.restart = {'old_key': child.key, 'binding': binding, 'state': 'ARMED', 'clicked': False,
                        'armed_at':time.monotonic(), 'acknowledged_at':None,
                        'restarter_key':None, 'replacement_key':None, 'provenance':'NONE'}

    def configure_restart_images(self, restarter, executable, launcher):
        from safe_io import read_regular
        self.check()
        if self.restart_images is not None:
            raise FamilyError('RESTART_IMAGES_ALREADY_SET')
        values={}
        for name,path in [('restarter',Path(restarter)),('executable',Path(executable)),('launcher',Path(launcher))]:
            raw=read_regular(path,limit=128*1024*1024)
            st=path.lstat()
            values[name]={'path':str(path),'sha256':hashlib.sha256(raw).hexdigest(),'dev':st.st_dev,'ino':st.st_ino,'size':st.st_size,'mtime_ns':st.st_mtime_ns}
        if values['restarter']['sha256']!='5b56e46d9126ec7eb71d0b298f2e1b41dc141300199d5afbdb49ceb1784e2586':
            raise FamilyError('RESTARER_BINARY_MISMATCH')
        self.restart_images=values

    def _born_after_arm(self, item):
        return int(item['meta']['start_time']) > int(self.restart['armed_at'] * os.sysconf('SC_CLK_TCK'))

    def terminal_child(self):
        self.check(); self.tick()
        if self.install_helpers is None or self.restart is None or self.restart['state'] != 'CLICK_DISPATCHED':
            raise FamilyError('TERMINAL_IDENTITY_INVALID')
        candidates = [item for item in self.members.values() if item.get('helper_kind') == 'TERMINAL']
        if len(candidates) > 1:
            raise FamilyError('MULTIPLE_INSTALL_TERMINALS')
        if not candidates:
            return None
        item = candidates[0]
        if (item['terminal'] or item['fd'] is None or not alive(item['fd'])
                or item['meta']['uid'] != self.owner['uid'] or item.get('lifecycle_only')
                or not self._born_after_arm(item)
                or not self._matches_binary(item['meta'], self.install_helpers['TERMINAL'])):
            raise FamilyError('TERMINAL_IDENTITY_INVALID')
        self.terminal_key = item['key']
        self.check()
        return Child(self, item['key'])

    def verify_terminal_helpers(self, child):
        self.check()
        terminal = self.terminal_child()
        if child.family is not self or terminal is None or terminal.key != child.key:
            raise FamilyError('TERMINAL_IDENTITY_INVALID')
        if not self._install_helpers_complete(child.key):
            self.terminal_verified_key = None
            return False
        self.terminal_verified_key = child.key
        self.check()
        return True

    def _install_helpers_complete(self, terminal_key):
        for item in self.members.values():
            if item.get('terminal_root') != terminal_key or not item.get('lifecycle_only'):
                continue
            if not item['terminal'] or (item['fd'] is not None and alive(item['fd'])):
                return False
            if item['exit_code'] is not None and item['exit_code'] != 0:
                raise FamilyError('INSTALL_HELPER_FAILED')
        return True

    def terminal_acknowledged(self, binding):
        self.check()
        if (self.restart is None or self.restart['state'] != 'CLICK_DISPATCHED'
                or self.restart['binding'] != binding or self.restart['acknowledged_at'] is not None
                or self.terminal_key is None or self.terminal_verified_key != self.terminal_key):
            raise FamilyError('TERMINAL_ACK_INVALID')
        # Called after the fresh bound Enter dispatch. The terminal may already
        # have exited; do not require its stale GUI authority to survive Enter.
        self.tick()
        if not self._install_helpers_complete(self.terminal_key):
            raise FamilyError('INSTALL_HELPERS_INCOMPLETE')
        self.restart['acknowledged_at'] = time.monotonic()
        self.check()

    def _image(self,item,name):
        if item['fd'] is None or not alive(item['fd']):return False
        expected=self.restart_images[name]
        try:before=info(item['meta']['pid'])
        except (FileNotFoundError,ProcessLookupError):
            if not alive(item['fd']):return False
            raise FamilyError('EXEC_IDENTITY_CHANGED')
        if stable(before)!=stable(item['meta']):raise FamilyError('EXEC_IDENTITY_CHANGED')
        try:path=os.readlink('/proc/'+str(before['pid'])+'/exe')
        except FileNotFoundError:return False
        if path!=expected['path']:return False
        st=Path(path).lstat()
        if any(getattr(st,'st_'+key)!=expected[key] for key in ('dev','ino','size','mtime_ns')):
            raise FamilyError('EXECUTABLE_CHANGED')
        actual=os.stat('/proc/'+str(before['pid'])+'/exe')
        if any(getattr(actual,'st_'+key)!=expected[key] for key in ('dev','ino','size','mtime_ns')):
            raise FamilyError('EXECUTABLE_CHANGED')
        return alive(item['fd']) and stable(info(before['pid']))==stable(before)

    def _observe_restart(self):
        transition=self.restart;old=self.members[transition['old_key']]
        acknowledged = transition['acknowledged_at']
        if acknowledged is not None and time.monotonic()>min(self.deadline,acknowledged+60):
            if transition['state'] not in ('RESTART_VERIFIED','CLOSED'):
                raise FamilyError('RESTART_DEADLINE')
        for item in list(self.members.values()):
            if item['terminal'] or item.get('helper_lineage') or item.get('lifecycle_only') or item['role'] in ('HELPER','TERMINAL_ONLY'):continue
            lineage=self.members.get(item.get('lineage'))
            if lineage and lineage['role']=='HELPER':continue
            if self._image(item,'restarter'):
                meta=info(item['meta']['pid'])
                if meta['ppid'] not in (old['meta']['pid'],self.owner['pid']):continue
                if not self._born_after_arm(item):continue
                with open('/proc/'+str(meta['pid'])+'/cmdline','rb') as stream:args=stream.read(4097)
                expected=[self.restart_images['restarter']['path'],str(old['meta']['pid']),'1',self.restart_images['launcher']['path']]
                if args!=b'\0'.join(os.fsencode(x) for x in expected)+b'\0':
                    raise FamilyError('RESTARER_COMMAND_MISMATCH')
                prior=transition['restarter_key']
                if prior is not None and prior!=item['key']:raise FamilyError('MULTIPLE_RESTARTERS')
                transition['restarter_key']=item['key'];item['role']='VENDOR_RESTARTER'
        key=transition['restarter_key']
        if old['terminal']:
            candidates=[]
            for item in self.members.values():
                if (item['terminal'] or item.get('helper_lineage') or item.get('lifecycle_only')
                        or item['role'] in ('HELPER','TERMINAL_ONLY') or item['fd'] is None or not alive(item['fd'])):continue
                try:meta=info(item['meta']['pid'])
                except (FileNotFoundError,ProcessLookupError):
                    if not alive(item['fd']):continue
                    raise FamilyError('EXEC_IDENTITY_CHANGED')
                if not self._born_after_arm(item):continue
                observed = key is not None and (item['key']==key or meta['ppid']==key[0])
                adopted = (item.get('adopted') and meta['ppid']==self.owner['pid']
                           and item['provenance'] in ('KERNEL_SUBREAPER_CHILD', 'VERIFIED_PARENT_CHILD')
                           and meta['session']==old['meta']['session']
                           and meta['pgrp']==old['meta']['pgrp'])
                if (observed or adopted) and self._image(item,'executable'):
                    candidates.append((item, 'OBSERVED_RESTARTER_EXEC' if observed else 'CLOSED_FAMILY_ADOPTED_EXEC'))
            if len(candidates)>1:raise FamilyError('MULTIPLE_REPLACEMENT_IDES')
            if candidates:
                item, provenance=candidates[0]
                prior=transition['replacement_key']
                if prior is not None and prior != item['key']:
                    raise FamilyError('MULTIPLE_REPLACEMENT_IDES')
                transition['replacement_key']=item['key']
                transition['provenance']=provenance
                item['role']='RESTARTED_IDE'

    def replacement(self):
        self.tick()
        if (self.restart is None or self.restart['state']!='CLICK_DISPATCHED'
                or self.restart['acknowledged_at'] is None):
            raise FamilyError('RESTART_NOT_DISPATCHED')
        key=self.restart['replacement_key']
        return Child(self,key) if key else None

    def verify_replacement(self,child):
        self.check();self.tick()
        if (self.restart is None or self.restart['state']!='CLICK_DISPATCHED'
                or self.restart['acknowledged_at'] is None or self.restart['replacement_key']!=child.key):
            raise FamilyError('REPLACEMENT_IDENTITY_INVALID')
        if not self._image(self.members[child.key],'executable'):
            raise FamilyError('REPLACEMENT_EXECUTABLE_INVALID')
        self.restart['state']='RESTART_VERIFIED'

    def restart_provenance(self):
        if self.restart is None or self.restart['state'] != 'RESTART_VERIFIED':
            return 'NONE'
        return self.restart['provenance']

    def permit_normal_close(self,child):
        self.check()
        if self.restart is None or self.restart['state']!='RESTART_VERIFIED' or child.key!=self.restart['replacement_key']:
            raise FamilyError('NORMAL_CLOSE_NOT_AUTHORIZED')
        self.normal_close_key=child.key

    def clicked(self, binding):
        self.check()
        if self.restart is None or self.restart['state'] != 'ARMED' or self.restart['binding'] != binding:
            raise FamilyError('RESTART_CLICK_INVALID')
        self.restart['clicked'] = True
        self.restart['state'] = 'CLICK_DISPATCHED'

    def close_phase(self):
        """No new launches until ECHILD + terminal ledger + no observation errors."""
        self.launches_closed = True
        self.cleanup_active = True
        # The existing cleanup grace is 3s TERM + 2s KILL. It grants no UI or
        # launch time after the absolute execution deadline.
        self.cleanup_deadline = time.monotonic() + 5
        errors = []
        try:
            for sig, seconds in ((signal.SIGTERM, 3), (signal.SIGKILL, 2)):
                until = min(self.cleanup_deadline, time.monotonic() + seconds)
                while time.monotonic() < until:
                    try:
                        self.tick()
                    except BaseException as exc:
                        errors.append(type(exc).__name__)
                    for item in self.members.values():
                        if (item['fd'] is not None and alive(item['fd']) and not item.get('never_signal')
                                and item['meta']['uid'] == self.owner['uid']):
                            try:
                                current = info(item['meta']['pid'])
                                if stable(current) != stable(item['meta']):
                                    raise FamilyError('REGISTERED_IDENTITY_CHANGED')
                                signal.pidfd_send_signal(item['fd'], sig)
                            except ProcessLookupError:
                                pass
                            except OSError:
                                errors.append('SIGNAL_FAILED')
                            except FamilyError:
                                errors.append('SIGNAL_IDENTITY_CHANGED')
                    try:
                        self._reap()
                    except BaseException as exc:
                        errors.append(type(exc).__name__)
                    if self.last_echild and all(i['terminal'] for i in self.members.values()):
                        break
                    time.sleep(.02)
                if self.last_echild and all(i['terminal'] for i in self.members.values()):
                    break
            try:
                empty = not children(self.owner, self.cleanup_deadline)
            except BaseException as exc:
                errors.append(type(exc).__name__); empty = False
            complete = (self.last_echild and empty and not self.pending_launch
                        and all(i['terminal'] for i in self.members.values())
                        and not errors and not self.observation_failed)
            self.phase_closed = complete
            if not complete:
                self.cancel.set('FAMILY_CLEANUP_INCOMPLETE')
                raise FamilyError('FAMILY_CLEANUP_INCOMPLETE')
            return {'status': 'FAMILY_CLEANUP_VERIFIED', 'registered': len(self.members), 'echild': True}
        finally:
            self.cleanup_active = False
            self.cleanup_deadline = None

    def begin_validation(self):
        self.check()
        if not self.phase_closed or self.restart is None or self.restart['state'] != 'RESTART_VERIFIED':
            raise FamilyError('VALIDATION_TRANSITION_FORBIDDEN')
        self._reap()
        if not self.last_echild:
            raise FamilyError('LIVE_CHILD_BLOCKS_VALIDATION')
        self.phase_closed = False
        self.launches_closed = False

    def close(self):
        self.launches_closed = True
        try:
            return self.close_phase()
        finally:
            self.closed = True
            os.close(self.parent_fd)
            for item in self.members.values():
                if item['fd'] is not None:
                    os.close(item['fd'])
                    item['fd'] = None
