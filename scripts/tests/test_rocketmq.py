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

    def invoke(self, output, command='clusterList', code=0, rpc_timeout='15'):
        env = dict(os.environ, JAVA_HOME=str(self.root), ROCKETMQ_HOME=str(self.root),
                   MOCK_ADMIN_OUTPUT=output, MOCK_ADMIN_EXIT=str(code), LAB_ADMIN_TIMEOUT_SECONDS=rpc_timeout)
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

    def test_rpc_timeout_override_remains_bounded(self):
        for value in ('0', '16', '-1', 'never'):
            self.assertEqual(self.invoke('', rpc_timeout=value).returncode, 2)

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
        (self.root / 'admin.sh').write_text((lab.INFRA / 'rocketmq/admin.sh').read_text())
        (self.root / 'logs.sh').write_text('#!/bin/sh\necho bounded-test-diagnostics\n')
        java = self.root / 'bin/java'
        java.write_text('''#!/bin/sh
printf called >> "$FAKE_ROOT/rpc.called"
case "$*" in
  *updateSubGroup*)
    if [ "${FAIL_GROUP_INIT:-false}" = true ]; then echo 'system group failed'; exit 1; fi
    printf "%s\n" "$@" > "$FAKE_ROOT/system-group.args"
    printf initialized > "$FAKE_ROOT/system-group.ready"
    echo 'create subscription group to 127.0.0.1:10911 success.'
    exit 0 ;;
esac
if [ "${BLOCK_RPC:-false}" = true ]; then
  trap 'printf stopped > "$FAKE_ROOT/rpc.stopped"; exit 0' TERM INT
  while :; do sleep 1; done
fi
if [ -f "$FAKE_ROOT/route.ready" ]; then
  echo 'LabCluster broker-a 0 127.0.0.1:10911 V5_3_2 stats true'
else
  echo '#Cluster Name  #Broker Name  #BID  #Addr'
fi
''')
        java.chmod(0o700)
        for command in ('mqnamesrv', 'mqbroker', 'mqproxy'):
            (self.root / 'bin' / command).write_text('''#!/bin/sh
name=$(basename "$0")
if [ "$name" = mqproxy ] && { [ ! -f "$FAKE_ROOT/route.ready" ] || [ ! -f "$FAKE_ROOT/system-group.ready" ]; }; then
  touch "$FAKE_ROOT/premature-proxy"
  exit 9
fi
printf '%s\\n' "$$" > "$FAKE_ROOT/$name.pid"
trap 'printf stopped > "$FAKE_ROOT/$name.stopped"; exit 0' TERM INT
if [ "${FAIL_PROCESS:-}" = "$name" ]; then sleep 0.3; exit 7; fi
while :; do sleep 1; done
''')

    def start(self, fail='', registered=True, block_rpc=False, fail_group=False):
        if registered:
            (self.root / 'route.ready').touch()
        env = dict(os.environ, JAVA_HOME=str(self.root), ROCKETMQ_HOME=str(self.root), FAKE_ROOT=str(self.root), FAIL_PROCESS=fail, BLOCK_RPC=str(block_rpc).lower(), FAIL_GROUP_INIT=str(fail_group).lower())
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

    def await_file(self, name):
        deadline = self.time.monotonic() + 5
        while not (self.root / name).exists():
            if self.time.monotonic() > deadline:
                self.fail('等待模拟文件超时：' + name)
            self.time.sleep(.02)

    def test_proxy_waits_for_actual_registered_broker_response(self):
        process = self.start(registered=False)
        self.await_file('mqbroker.pid')
        self.await_file('rpc.called')
        self.assertFalse((self.root / 'mqproxy.pid').exists())
        (self.root / 'route.ready').touch()
        self.await_file('mqproxy.pid')
        process.terminate()
        out, err = process.communicate(timeout=5)
        self.assertEqual(process.returncode, 0, out + err)
        self.assertFalse((self.root / 'premature-proxy').exists())
        self.assertIn('Broker 注册屏障通过', out)
        self.assertIn('CID_DefaultHeartBeatSyncerTopic\n-d\ntrue', (self.root / 'system-group.args').read_text())

    def test_missing_registration_times_out_without_starting_proxy(self):
        self.script.write_text(self.script.read_text().replace('REGISTER_WAIT_SECONDS=120', 'REGISTER_WAIT_SECONDS=2'))
        process = self.start(registered=False)
        out, err = process.communicate(timeout=6)
        self.assertEqual(process.returncode, 1, out + err)
        self.assertIn('注册屏障未通过', err)
        self.assertIn('#Cluster Name', err)
        self.assertFalse((self.root / 'mqproxy.pid').exists())
        self.assertTrue((self.root / 'mqnamesrv.stopped').exists())
        self.assertTrue((self.root / 'mqbroker.stopped').exists())

    def test_broker_failure_during_registration_cleans_nameserver(self):
        process = self.start('mqbroker', registered=False)
        out, err = process.communicate(timeout=5)
        self.assertEqual(process.returncode, 1, out + err)
        self.assertIn('可用路由出现前退出', err)
        self.assertFalse((self.root / 'mqproxy.pid').exists())
        self.assertTrue((self.root / 'mqnamesrv.stopped').exists())

    def test_term_during_registration_cleans_started_services(self):
        process = self.start(registered=False)
        self.await_file('rpc.called')
        process.terminate()
        out, err = process.communicate(timeout=5)
        self.assertEqual(process.returncode, 0, out + err)
        self.assertFalse((self.root / 'mqproxy.pid').exists())
        self.assertTrue((self.root / 'mqnamesrv.stopped').exists())
        self.assertTrue((self.root / 'mqbroker.stopped').exists())

    def test_term_during_active_registration_rpc_reaches_tool_process(self):
        process = self.start(registered=False, block_rpc=True)
        self.await_file('rpc.called')
        process.terminate()
        out, err = process.communicate(timeout=5)
        self.assertEqual(process.returncode, 0, out + err)
        self.assertTrue((self.root / 'rpc.stopped').exists())
        self.assertFalse((self.root / 'mqproxy.pid').exists())
        self.assertTrue((self.root / 'mqnamesrv.stopped').exists())
        self.assertTrue((self.root / 'mqbroker.stopped').exists())

    def test_system_group_failure_does_not_start_proxy(self):
        process = self.start(fail_group=True)
        out, err = process.communicate(timeout=5)
        self.assertEqual(process.returncode, 1, out + err)
        self.assertIn('系统消费组初始化失败', err)
        self.assertFalse((self.root / 'mqproxy.pid').exists())
        self.assertTrue((self.root / 'mqnamesrv.stopped').exists())
        self.assertTrue((self.root / 'mqbroker.stopped').exists())

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
