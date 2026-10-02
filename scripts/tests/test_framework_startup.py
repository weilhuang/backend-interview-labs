"""Bounded startup regressions: temporary files and our own short-lived children only.

A shell function delays this fixture's nohup exec in its real background child.
The normal delayed-exec case uses real ps output unchanged. Negative identity and
timeout cases alter only this fixture PID's ps output. curl is an audited stub;
no network request, Java or Gradle execution occurs.
"""
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / 'courses/java-frameworks/scripts/course.sh'


class FrameworkStartupTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='framework-startup-test-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.state = self.root / 'build/server'
        self.state.mkdir(parents=True)
        (self.root / 'scripts').mkdir()
        self.script = self.root / 'scripts/course.sh'
        shutil.copy2(os.environ.get('FRAMEWORK_STARTUP_SCRIPT', SOURCE), self.script)
        self.bin = self.root / 'bin'
        self.bin.mkdir()
        self.environment = dict(os.environ, PATH=str(self.bin) + os.pathsep + os.environ['PATH'],
                                JAVA_HOME=str(self.root), LAB_GRADLE_BIN=str(self.bin / 'gradle'),
                                FIXTURE_ROOT=str(self.root), FIXTURE_PYTHON=sys.executable,
                                FIXTURE_PS=shutil.which('ps'), FIXTURE_MODE='delayed',
                                FIXTURE_NOHUP=shutil.which('nohup'),
                                BASH_ENV=str(self.root / 'launch-delay.sh'))
        (self.root / 'launch-delay.sh').write_text('''nohup() {
  printf 'delayed own child exec\\n' > "$FIXTURE_ROOT/launch-delayed"
  /bin/sleep 0.3
  if [[ "$FIXTURE_MODE" == early_exit ]]; then return 7; fi
  exec "$FIXTURE_NOHUP" "$@"
}
''')
        self.write_executable('gradle', '''#!/usr/bin/env bash
set -eu
mkdir -p framework-course/01-boot/02-http-contract/build
printf 'fixture-only-classpath\\n' > framework-course/01-boot/02-http-contract/build/verification-classpath.txt
''')
        self.write_executable('java', '''#!PYTHON
import os, pathlib, sys, time
root=pathlib.Path(os.environ['FIXTURE_ROOT'])
os.execv(sys.executable,[sys.executable,str(root/'worker.py'),*sys.argv[1:]])
''')
        (self.root / 'worker.py').write_text('''import os,pathlib,time
root=pathlib.Path(os.environ['FIXTURE_ROOT'])
(root/'exec-ready').write_text('ready')
time.sleep(30)
''')
        self.write_executable('ps', '''#!PYTHON
import json,os,pathlib,subprocess,sys
root=pathlib.Path(os.environ['FIXTURE_ROOT']);args=sys.argv[1:]
result=subprocess.run([os.environ['FIXTURE_PS'],*args],capture_output=True,text=True)
query=args[args.index('-p')+1] if '-p' in args else ''
file=root/'build/server/pid'
ours=file.exists() and query==file.read_text().strip()
mode=os.environ['FIXTURE_MODE']
if ours and result.returncode==0:
 if 'lstart=' in args and mode=='changed_identity':
  count=root/'identity-count';n=int(count.read_text()) if count.exists() else 0;count.write_text(str(n+1))
  if n: result.stdout=result.stdout.replace('2026','2025')+' changed'
 if 'command=' in args:
  if mode=='wrong_identity': result.stdout='fixture-worker-without-course-identity\\n'
  elif mode in ('transition_commands','empty_command_transition'):
   count=root/'transition-observations';n=int(count.read_text()) if count.exists() else 0;count.write_text(str(n+1))
   if n<2: result.stdout=('fixture-intermediate-exec-without-final-flags' if mode=='transition_commands' else '')+'\\n'
  elif mode=='startup_timeout':
   parent=subprocess.check_output([os.environ['FIXTURE_PS'],'-p',query,'-o','ppid='],text=True).strip()
   result.stdout=subprocess.check_output([os.environ['FIXTURE_PS'],'-ww','-p',parent,'-o','command='],text=True)
   with (root/'pending-observations').open('a') as output: output.write('pending\\n')
sys.stdout.write(result.stdout);sys.stderr.write(result.stderr);sys.exit(result.returncode)
''')
        self.write_executable('sleep', '''#!PYTHON
import os,pathlib,sys,time
root=pathlib.Path(os.environ['FIXTURE_ROOT'])
with (root/'sleeps').open('a') as output: output.write(sys.argv[1]+'\\n')
if os.environ['FIXTURE_MODE']=='startup_timeout': sys.exit(0)
time.sleep(min(float(sys.argv[1]),0.02))
''')
        self.write_executable('curl', '''#!PYTHON
import json,os,pathlib,signal,sys
root=pathlib.Path(os.environ['FIXTURE_ROOT']);file=root/'curl-calls'
with file.open('a') as output: output.write(json.dumps(sys.argv[1:])+'\\n')
calls=len(file.read_text().splitlines());mode=os.environ['FIXTURE_MODE']
if mode in ('http_exit','http_exit_success'):
 os.kill(int((root/'build/server/pid').read_text()),signal.SIGTERM)
 if mode=='http_exit': sys.exit(22)
if mode=='http_timeout' or (mode=='http_retry' and calls<3): sys.exit(22)
args=sys.argv[1:]
headers=pathlib.Path(args[args.index('--dump-header')+1]);body=pathlib.Path(args[args.index('--output')+1])
token=(root/'build/server/token').read_text().strip()
headers.write_text('HTTP/1.1 200 OK\\r\\nX-Framework-Lab-Instance: '+token+'\\r\\n\\r\\n')
body.write_text('[]')
print('200',end='')
''')
        self.addCleanup(self.clean_child)

    def write_executable(self, name, content):
        path = self.bin / name
        path.write_text(content.replace('#!PYTHON', '#!' + sys.executable))
        path.chmod(0o755)

    def clean_child(self):
        # Exactly the single child PID launched in this fixture, no process scans/groups.
        path = self.state / 'pid'
        if path.exists():
            pid = int(path.read_text())
            command = subprocess.run([self.environment['FIXTURE_PS'], '-ww', '-p', str(pid),
                                      '-o', 'command='], capture_output=True, text=True).stdout
            if str(self.root) in command:
                try: os.kill(pid, signal.SIGTERM)
                except ProcessLookupError: pass

    def run_course(self, action, expected=0):
        result = subprocess.run(['bash', str(self.script), action], env=self.environment,
                                capture_output=True, text=True, timeout=25)
        self.assertEqual(result.returncode, expected, (result.stdout, result.stderr))
        return result

    def calls(self):
        path = self.root / 'curl-calls'
        return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []

    def test_delayed_same_child_exec_then_separate_http_check(self):
        self.run_course('start')
        self.assertTrue((self.root / 'launch-delayed').exists())
        self.assertIn('0.1', (self.root / 'sleeps').read_text().splitlines())
        self.assertEqual(self.calls(), [])
        self.run_course('check')
        self.assertEqual(len(self.calls()), 1)
        self.assertIn('--max-time', self.calls()[0])
        self.run_course('stop')

    def test_unknown_exec_transitions_wait_for_final_identity_without_http(self):
        self.environment['FIXTURE_MODE']='transition_commands'
        result=self.run_course('start')
        self.assertGreaterEqual(int((self.root/'transition-observations').read_text()),3)
        self.assertTrue((self.root/'exec-ready').exists())
        self.assertLessEqual(result.stderr.count('启动过渡观察'),3)
        self.assertNotIn((self.state/'token').read_text().strip(),result.stderr)
        self.assertEqual(self.calls(),[])
        self.run_course('check');self.assertEqual(len(self.calls()),1);self.run_course('stop')

    def test_empty_exec_command_does_not_become_ready_until_final_identity(self):
        self.environment['FIXTURE_MODE']='empty_command_transition'
        result=self.run_course('start')
        self.assertGreaterEqual(int((self.root/'transition-observations').read_text()),3)
        self.assertIn('command_chars=0',result.stderr)
        self.assertTrue((self.root/'exec-ready').exists())
        self.assertEqual(self.calls(),[]);self.run_course('stop')

    def test_early_exit_fails_without_http(self):
        self.environment['FIXTURE_MODE'] = 'early_exit'
        self.run_course('start', 1)
        self.assertEqual(self.calls(), [])

    def test_wrong_identity_fails_without_http(self):
        self.environment['FIXTURE_MODE'] = 'wrong_identity'
        result=self.run_course('start', 1)
        self.assertIn('身份不匹配',result.stdout)
        self.assertIn('超时',result.stdout)
        self.assertLessEqual(result.stderr.count('启动过渡观察'),3)
        self.assertEqual(self.calls(), [])

    def test_changed_parent_start_time_fails_without_http(self):
        self.environment['FIXTURE_MODE'] = 'changed_identity'
        self.assertIn('身份已改变', self.run_course('start', 1).stdout)
        self.assertEqual(self.calls(), [])

    def test_startup_timeout_is_bounded_and_not_ready(self):
        self.environment['FIXTURE_MODE'] = 'startup_timeout'
        self.assertIn('超时', self.run_course('start', 1).stdout)
        sleeps=(self.root / 'sleeps').read_text().splitlines()
        self.assertTrue(1<=len(sleeps)<=100)
        self.assertTrue(all(value=='0.1' for value in sleeps))
        self.assertEqual(self.calls(), [])

    def test_http_retry_is_separate_from_process_start(self):
        self.run_course('start')
        self.environment['FIXTURE_MODE'] = 'http_retry'
        self.run_course('check')
        self.assertEqual(len(self.calls()), 3)

    def test_http_timeout_stays_failed(self):
        self.run_course('start')
        self.environment['FIXTURE_MODE'] = 'http_timeout'
        self.assertIn('尚未就绪', self.run_course('check', 1).stdout)
        self.assertEqual(len(self.calls()), 30)

    def test_child_exit_between_http_attempts_stops_probing(self):
        self.run_course('start')
        self.environment['FIXTURE_MODE'] = 'http_exit'
        self.assertIn('服务未运行', self.run_course('check', 1).stdout)
        self.assertEqual(len(self.calls()), 1)

    def test_child_exit_with_successful_response_is_not_ready(self):
        self.run_course('start')
        self.environment['FIXTURE_MODE'] = 'http_exit_success'
        self.assertIn('HTTP响应后', self.run_course('check', 1).stdout)
        self.assertEqual(len(self.calls()), 1)

    def test_check_wrong_identity_never_probes_http(self):
        self.run_course('start')
        self.environment['FIXTURE_MODE'] = 'wrong_identity'
        self.assertIn('实例身份不匹配', self.run_course('check', 1).stdout)
        self.assertEqual(self.calls(), [])

    def test_existing_process_control_contract(self):
        result = subprocess.run([sys.executable, str(SOURCE.with_name('test-process-control.py'))],
                                capture_output=True, text=True, timeout=25)
        self.assertEqual(result.returncode, 0, (result.stdout, result.stderr))
        self.assertEqual(len(json.loads(result.stdout)['cases']), 9)


if __name__ == '__main__':
    unittest.main()
