#!/usr/bin/env python3
"""在隔离临时目录验证进程控制，不启动数据库、不操作既有课程服务。"""
from pathlib import Path
import json, os, shutil, subprocess, sys, tempfile, time
SOURCE = Path(__file__).resolve().parent / 'course.sh'
TOKEN = '1' * 32
CASES = []
with tempfile.TemporaryDirectory(prefix='framework-process-check-') as temporary:
    root = Path(temporary)
    (root/'scripts').mkdir()
    shutil.copy2(SOURCE, root/'scripts/course.sh')
    state = root/'build/server'
    state.mkdir(parents=True)
    script = root/'scripts/course.sh'

    def run(expected, action='stop'):
        result = subprocess.run(['bash', str(script), action], text=True, capture_output=True, timeout=15)
        assert result.returncode == expected, (result.returncode, result.stdout, result.stderr)
        return result.stdout.strip()

    def record(pid, token=TOKEN):
        (state/'pid').write_text(str(pid)+'\n')
        (state/'token').write_text(token+'\n')

    def worker(token=TOKEN, marker=True):
        # 只创建本测试的受控子进程；参数模拟被ps核验的实例标记与主类。
        args = [sys.executable, '-c', 'import time; time.sleep(30)', '-Dframework.lab.token='+token]
        if marker: args.append('labs.frameworks.Lab')
        return subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    CASES.append({'case':'无PID文件幂等停止','result':run(0)})
    record(-1)
    CASES.append({'case':'非法PID不能向进程组发信号','result':run(1)})
    record(2147483647)
    CASES.append({'case':'不存在PID清除过期记录','result':run(0)})
    assert not (state/'pid').exists()

    foreign = worker('2'*32)
    try:
        record(foreign.pid)
        CASES.append({'case':'复用PID但token不匹配不误杀','result':run(1)})
        assert foreign.poll() is None
        CASES.append({'case':'身份错误时check不探测其他HTTP服务','result':run(1,'check')})
    finally:
        foreign.terminate(); foreign.wait(timeout=5)

    no_marker = worker(marker=False)
    try:
        record(no_marker.pid)
        CASES.append({'case':'token相同但主类不匹配不误杀','result':run(1)})
        assert no_marker.poll() is None
    finally:
        no_marker.terminate(); no_marker.wait(timeout=5)

    stopped = worker()
    stopped.terminate(); stopped.wait(timeout=5)
    record(stopped.pid)
    CASES.append({'case':'已经退出的PID安全清理','result':run(0)})

    owned = worker()
    try:
        record(owned.pid)
        CASES.append({'case':'身份匹配只终止本测试子进程','result':run(0)})
        owned.wait(timeout=5)
        assert not (state/'pid').exists() and not (state/'token').exists()
        CASES.append({'case':'重复stop幂等','result':run(0)})
    finally:
        if owned.poll() is None: owned.terminate(); owned.wait(timeout=5)

print(json.dumps({'status':'passed','platform':sys.platform,'cases':CASES,
                  'macos':'使用macOS支持的ps参数与Bash3语法；未在真实macOS执行，不能标记跨平台实测通过'},ensure_ascii=False,indent=2))
