"""Own loopback HTTP fixture plus an independent owned child; never contact an existing service."""
import http.server
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / 'courses/java-frameworks/scripts/course.sh'
TOKEN = '0123456789abcdef0123456789abcdef'


class FrameworkHttpIdentityTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='framework-http-identity-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.responses = []
        self.requests = []
        owner = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                owner.requests.append((self.path, dict(self.headers)))
                body = b'[]\n'
                self.send_response(200)
                for name, value in owner.responses:
                    self.send_header(name, value)
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):
                pass

        # Bind a new ephemeral loopback listener; only the fixture copy's URL changes.
        self.server = http.server.HTTPServer(('127.0.0.1', 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.close_server)
        (self.root / 'scripts').mkdir()
        self.script = self.root / 'scripts/course.sh'
        source = Path(os.environ.get('FRAMEWORK_STARTUP_SCRIPT', SOURCE)).read_text()
        self.assertEqual(source.count('http://127.0.0.1:18084/api/orders'), 1)
        self.script.write_text(source.replace('http://127.0.0.1:18084/api/orders',
            'http://127.0.0.1:' + str(self.server.server_port) + '/api/orders'))
        self.child = subprocess.Popen([sys.executable, '-c', 'import time;time.sleep(30)',
            '-Dframework.lab.token=' + TOKEN, '-Dframework.lab.instance=' + str(self.root),
            'labs.frameworks.Lab'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.addCleanup(self.close_child)
        self.state = self.root / 'build/server'
        self.state.mkdir(parents=True)
        (self.state / 'pid').write_text(str(self.child.pid) + '\n')
        (self.state / 'token').write_text(TOKEN + '\n')

    def close_child(self):
        if self.child.poll() is None:
            self.child.terminate()
        self.child.wait(timeout=5)

    def close_server(self):
        self.server.shutdown()
        self.thread.join(timeout=5)
        self.server.server_close()

    def check(self, expected):
        result = subprocess.run(['bash', str(self.script), 'check'], capture_output=True,
                                text=True, timeout=5)
        self.assertEqual(result.returncode, expected, (result.stdout, result.stderr))
        self.assertIsNone(self.child.poll())
        self.assertEqual(len(self.requests), 1)
        path, headers = self.requests[0]
        self.assertEqual(path, '/api/orders')
        self.assertNotIn(TOKEN, path + str(headers))
        if expected:
            self.assertIn('HTTP响应实例标记不匹配', result.stdout)
        return result

    def test_other_200_without_header_is_rejected(self):
        self.check(1)

    def test_other_200_with_wrong_header_is_rejected(self):
        self.responses = [('X-Framework-Lab-Instance', 'f' * 32)]
        self.check(1)

    def test_duplicate_matching_headers_are_rejected(self):
        self.responses = [('X-Framework-Lab-Instance', TOKEN)] * 2
        self.check(1)

    def test_duplicate_empty_trailing_header_is_rejected(self):
        self.responses = [('X-Framework-Lab-Instance', TOKEN), ('X-Framework-Lab-Instance', '')]
        self.check(1)

    def test_duplicate_empty_leading_header_is_rejected(self):
        self.responses = [('X-Framework-Lab-Instance', ''), ('X-Framework-Lab-Instance', TOKEN)]
        self.check(1)

    def test_three_instance_headers_are_rejected(self):
        self.responses = [('X-Framework-Lab-Instance', TOKEN),
                          ('x-framework-lab-instance', 'f' * 32),
                          ('X-Framework-Lab-Instance', TOKEN)]
        self.check(1)

    def test_correct_single_header_and_live_instance_succeed(self):
        self.responses = [('X-Framework-Lab-Instance', TOKEN)]
        self.assertIn('实例标记匹配', self.check(0).stdout)

    def test_header_name_is_case_insensitive(self):
        self.responses = [('x-framework-lab-instance', '  ' + TOKEN + '\t')]
        self.check(0)

    def test_header_value_cannot_hide_suffix_after_colon(self):
        self.responses = [('X-Framework-Lab-Instance', TOKEN + ':invalid')]
        self.check(1)


if __name__ == '__main__':
    unittest.main()
