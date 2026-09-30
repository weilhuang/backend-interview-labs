"""真实冒烟入口本身的离线回归；不把模拟读写算作组件验证。"""
import contextlib
import io
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import ci_smoke

class SmokeTests(unittest.TestCase):
    def setUp(self):
        self.config = {'LAB_PROJECT_NAME':'backend-interview-labs-ci-123-1', 'MYSQL_PASSWORD':'lab_private_mysql',
                       'MYSQL_ROOT_PASSWORD':'lab_private_root', 'REDIS_PASSWORD':'lab_private_redis'}
        self.context = patch.object(ci_smoke, 'guarded_config', return_value=(self.config, Path('/mock/.env')))

    def invoke(self, action):
        with contextlib.redirect_stdout(io.StringIO()):
            ci_smoke.main(action)

    def test_non_ci_refused(self):
        with patch.object(ci_smoke.lab,'settings',return_value=(self.config,Path('/mock/.env'))), patch.dict(os.environ,{'CI':'false'}):
            with self.assertRaises(ci_smoke.lab.LabError):
                ci_smoke.guarded_config()

    def test_learning_project_refused(self):
        self.config['LAB_PROJECT_NAME']='backend-interview-labs'
        with patch.object(ci_smoke.lab,'settings',return_value=(self.config,Path('/mock/.env'))), patch.dict(os.environ,{'CI':'true'}):
            with self.assertRaises(ci_smoke.lab.LabError):
                ci_smoke.guarded_config()

    def test_exact_ci_project_allowed(self):
        with patch.object(ci_smoke.lab,'settings',return_value=(self.config,Path('/mock/.env'))), patch.dict(os.environ,{'CI':'true'}):
            self.assertEqual(ci_smoke.guarded_config()[0],self.config)

    def test_core_write_passes_redis_arguments_through_shell(self):
        marker=self.config['LAB_PROJECT_NAME']
        with self.context, patch.object(ci_smoke,'execute',side_effect=[marker,'OK',marker]) as execute:
            self.invoke('core-write')
        command=execute.call_args_list[1].args[3]
        self.assertIn('"$@"',command[2])
        self.assertEqual(command[3:],['redis-cli','SET','lab:ci:smoke',marker])

    def test_core_persistence_requires_both_values(self):
        marker=self.config['LAB_PROJECT_NAME']
        with self.context, patch.object(ci_smoke,'execute',side_effect=[marker,'']):
            with self.assertRaises(ci_smoke.lab.LabError):
                self.invoke('core-read')

    def test_mysql_wrong_value_fails_before_redis(self):
        with self.context, patch.object(ci_smoke,'execute',return_value='wrong') as execute:
            with self.assertRaises(ci_smoke.lab.LabError):
                self.invoke('core-write')
        self.assertEqual(execute.call_count,1)

    def test_kafka_real_sequence_and_marker(self):
        marker=self.config['LAB_PROJECT_NAME']
        with self.context, patch.object(ci_smoke,'execute',side_effect=['','',marker]) as execute:
            self.invoke('kafka')
        self.assertIn('kafka-topics.sh',execute.call_args_list[0].args[3][0])
        self.assertEqual(execute.call_args_list[1].args[4],marker+'\n')
        self.assertIn('--max-messages',execute.call_args_list[2].args[3])

    def test_kafka_wrong_message_fails(self):
        with self.context, patch.object(ci_smoke,'execute',side_effect=['','','wrong']):
            with self.assertRaises(ci_smoke.lab.LabError):
                self.invoke('kafka')

    def test_logs_redact_all_config_passwords(self):
        with tempfile.TemporaryDirectory() as name:
            root=Path(name)
            (root/'infra').mkdir()
            result=subprocess.CompletedProcess([],0,'lab_private_mysql lab_private_root lab_private_redis','')
            with self.context, patch.object(ci_smoke.lab,'ROOT',root), patch.object(ci_smoke.lab,'compose',return_value=['docker']), patch.object(ci_smoke.lab,'docker_env',return_value={}), patch.object(ci_smoke.subprocess,'run',return_value=result):
                self.invoke('logs')
            for file in (root/'infra'/'artifacts').glob('*.log'):
                self.assertNotIn('lab_private_',file.read_text())
                self.assertIn('[已脱敏]',file.read_text())

if __name__ == '__main__':
    unittest.main(verbosity=2)
