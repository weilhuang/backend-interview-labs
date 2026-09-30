"""Bounded POSIX subprocess groups for quality gates; never global process matching."""
import os
from pathlib import Path
import signal
import subprocess
import time

TERMINATION_GRACE = 15


def check_support():
    if (not all(hasattr(os, name) for name in ('WNOWAIT', 'WNOHANG', 'WEXITED', 'P_PID'))
            or not callable(getattr(os, 'waitid', None)) or not callable(getattr(os, 'killpg', None))):
        raise OSError('Author/CI quality scripts need POSIX waitid/WNOWAIT. On macOS use Python 3.13 or newer; '
                      'Linux CI Python 3.12 is supported. No work fixture has been created. '
                      'Ordinary IDEA/Gradle student commands do not require Python.')


def _wait_unreaped(process, seconds):
    deadline = time.monotonic() + seconds
    while True:
        # Observe without reaping. Popen.wait is deliberately not used here: its
        # KeyboardInterrupt handler may reap the leader before group cleanup.
        if os.waitid(os.P_PID, process.pid, os.WEXITED | os.WNOHANG | os.WNOWAIT) is not None:
            return True
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return False
        time.sleep(min(0.05, remaining))


def _kill_and_reap(process):
    # The unreaped leader reserves this PID/group identity until after the kill.
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    return process.wait()


def _terminate_group(process, grace):
    try:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        _wait_unreaped(process, grace)
    finally:
        # A second interrupt during the grace period must not skip the kill.
        code = _kill_and_reap(process)
    return code


def run_logged(command, *, log: Path, timeout, cwd=None, env=None):
    """Return exit code; timeout/interrupt terminate only this new session/group.

    `timeout` includes up to 15 seconds for group termination. Logs survive all
    outcomes. Docker resources are separate; callers must keep Ryuk enabled.
    """
    if timeout <= TERMINATION_GRACE:
        raise ValueError('process budget must include the 15-second termination reserve')
    check_support()
    with log.open('w', encoding='utf-8') as output:
        process = subprocess.Popen(command, cwd=cwd, env=env, stdout=output,
                                   stderr=subprocess.STDOUT, start_new_session=True)
        try:
            if not _wait_unreaped(process, timeout - TERMINATION_GRACE):
                raise subprocess.TimeoutExpired(command, timeout)
        except (subprocess.TimeoutExpired, KeyboardInterrupt):
            _terminate_group(process, TERMINATION_GRACE)
            raise
        # Even normal leader exit must not leave detached work in its group.
        # No other process can reuse its PID until the following final wait.
        return _kill_and_reap(process)
