"""管理命令输出、HTTP/2 探针和多进程监督的离线回归；不是 RocketMQ 集成测试。"""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import lab


class Http2Tests(unittest.TestCase):
    def probe(self, frames):
        connection = MagicMock()
        data = bytearray(frames)
        def receive(size):
            # 模拟短读，防止错误依赖 recv 一次必定填满。
            count = min(size, 3)
            value = bytes(data[:count])
            del data[:count]
            return value
        connection.recv.side_effect = receive
        connection.__enter__.return_value = connection
        with patch.object(lab.socket, 'create_connection', return_value=connection):
            lab.probe_http2('127.0.0.1', 18081)
        return connection

    @staticmethod
    def frame(kind, flags=0, payload=b'', stream=0):
        return len(payload).to_bytes(3, 'big') + bytes([kind, flags]) + stream.to_bytes(4, 'big') + payload

    def test_matching_ping_requires_settings_and_round_trip(self):
        sock = self.probe(self.frame(4) + self.frame(4, 1) + self.frame(6, 1, b'LABREADY'))
        self.assertEqual(sock.sendall.call_count, 3)
        self.assertTrue(sock.sendall.call_args_list[0].args[0].startswith(b'PRI * HTTP/2.0'))
        self.assertTrue(sock.sendall.call_args_list[-1].args[0].endswith(b'LABREADY'))

    def test_tcp_connect_without_protocol_is_not_ready(self):
        with self.assertRaises(ValueError):
            self.probe(b'')

    def test_ping_before_settings_is_not_ready(self):
        with self.assertRaises(ValueError):
            self.probe(self.frame(6, 1, b'LABREADY'))

    def test_nonmatching_ping_is_not_ready(self):
        with self.assertRaises(ValueError):
            self.probe(self.frame(4) + self.frame(6, 1, b'OTHERACK'))

    def test_goaway_is_not_ready(self):
        with self.assertRaisesRegex(ValueError, 'GOAWAY'):
            self.probe(self.frame(7))

    def test_oversized_frame_is_not_read_into_memory(self):
        with self.assertRaises(ValueError):
            self.probe((16385).to_bytes(3, 'big') + b'\x04\0\0\0\0\0')

    def test_settings_nonzero_stream_is_rejected(self):
        with self.assertRaises(ValueError):
            self.probe(self.frame(4, stream=1))


class AdminTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'bin').mkdir()
        java = self.root / 'bin' / 'java'
        java.write_text('#!/bin/sh\nprintf "%s\\n" "$MOCK_ADMIN_OUTPUT"\nexit "${MOCK_ADMIN_EXIT:-0}"\n')
        java.chmod(0o700)

    def invoke(self, output, command='clusterList', code=0):
        env = dict(os.environ, JAVA_HOME=str(self.root), ROCKETMQ_HOME=str(self.root),
                   MOCK_ADMIN_OUTPUT=output, MOCK_ADMIN_EXIT=str(code))
        return subprocess.run(['bash', str(lab.INFRA / 'rocketmq' / 'admin.sh'), command],
                              env=env, capture_output=True, text=True, timeout=20)

    def test_real_broker_row_with_version_and_active_is_required(self):
        self.assertEqual(self.invoke('LabCluster  broker-a  0  127.0.0.1:10911  V5_3_2  stats  true').returncode, 0)

    def test_empty_cluster_header_is_not_success(self):
        self.assertNotEqual(self.invoke('#Cluster Name  #Broker Name  #BID  #Addr').returncode, 0)

    def test_inactive_broker_is_not_success(self):
        self.assertNotEqual(self.invoke('LabCluster broker-a 0 127.0.0.1:10911 V5_3_2 stats false').returncode, 0)

    def test_exception_with_zero_exit_is_failure(self):
        output = 'LabCluster broker-a 0 127.0.0.1:10911 V5_3_2 stats true\norg.apache.FooException: failed'
        self.assertNotEqual(self.invoke(output).returncode, 0)

    def test_nonzero_exit_is_failure_even_with_success_output(self):
        self.assertNotEqual(self.invoke('create topic to 127.0.0.1:10911 success.', 'updateTopic', 1).returncode, 0)

    def test_each_write_requires_its_own_success_evidence(self):
        self.assertEqual(self.invoke('create topic to 127.0.0.1:10911 success.', 'updateTopic').returncode, 0)
        self.assertEqual(self.invoke('create subscription group to 127.0.0.1:10911 success.', 'updateSubGroup').returncode, 0)
        self.assertNotEqual(self.invoke('', 'updateSubGroup').returncode, 0)

    def test_unknown_admin_command_is_rejected(self):
        self.assertEqual(self.invoke('', 'deleteTopic').returncode, 2)

class SupervisorTests(unittest.TestCase):
    def setUp(self):
        import time
        self.time = time
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'bin').mkdir()
        (self.root / 'conf').mkdir()
        source = (lab.INFRA / 'rocketmq' / 'start.sh').read_text()
        source = source.replace('LAB_DATA=/tmp/lab-rocketmq', 'LAB_DATA=' + str(self.root / 'data'))
        self.script = self.root / 'start.sh'
        self.script.write_text(source)
        for command in ('mqnamesrv', 'mqbroker', 'mqproxy'):
            (self.root / 'bin' / command).write_text('''#!/bin/sh
name=$(basename "$0")
printf '%s\\n' "$$" > "$FAKE_ROOT/$name.pid"
trap 'printf stopped > "$FAKE_ROOT/$name.stopped"; exit 0' TERM INT
if [ "${FAIL_PROCESS:-}" = "$name" ]; then sleep 0.3; exit 7; fi
while :; do sleep 1; done
''')

    def start(self, fail=''):
        env = dict(os.environ, ROCKETMQ_HOME=str(self.root), FAKE_ROOT=str(self.root), FAIL_PROCESS=fail)
        process = subprocess.Popen(['bash', str(self.script)], env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        def cleanup():
            if process.poll() is None:
                process.terminate()
                try:
                    process.communicate(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.communicate()
        self.addCleanup(cleanup)
        return process

    def test_term_reaches_all_three_services(self):
        process = self.start()
        deadline = self.time.monotonic() + 5
        while len(list(self.root.glob('*.pid'))) != 3:
            self.assertIsNone(process.poll(), '监督进程提前退出')
            if self.time.monotonic() > deadline:
                self.fail('模拟子进程未按时启动')
            self.time.sleep(.02)
        process.terminate()
        out, err = process.communicate(timeout=5)
        self.assertEqual(process.returncode, 0, out + err)
        self.assertEqual(len(list(self.root.glob('*.stopped'))), 3)
        proxy = (self.root / 'data' / 'proxy.json').read_text()
        self.assertIn('"proxyMode":"CLUSTER"', proxy)
        self.assertIn('"useEndpointPortFromRequest":true', proxy)

    def test_child_failure_stops_remaining_services_and_is_nonzero(self):
        process = self.start('mqproxy')
        out, err = process.communicate(timeout=5)
        self.assertEqual(process.returncode, 7, out + err)
        self.assertTrue((self.root / 'mqnamesrv.stopped').exists())
        self.assertTrue((self.root / 'mqbroker.stopped').exists())


if __name__ == '__main__':
    unittest.main(verbosity=2)
