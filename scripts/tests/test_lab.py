"""无 Docker 的行为与配置回归测试；模拟结果不代表容器实际可运行。"""
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location('lab', Path(__file__).resolve().parents[1] / 'lab.py')
lab = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(lab)
SOURCE = lab.ROOT

class LabTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='课程 环境-')
        self.root = Path(self.temp.name)
        shutil.copytree(SOURCE / 'infra', self.root / 'infra', ignore=shutil.ignore_patterns('.env'))
        (self.root / 'courses' / '示例课程').mkdir(parents=True)
        self.patches = [patch.object(lab, 'ROOT', self.root), patch.object(lab, 'INFRA', self.root / 'infra')]
        for p in self.patches:
            p.start()
        self.addCleanup(self.temp.cleanup)
        self.addCleanup(lambda: [p.stop() for p in self.patches])
        self.config, self.envpath = lab.settings()

    def write_config(self, **changes):
        config = dict(self.config)
        config.update(changes)
        (lab.INFRA / '.env').write_text(''.join(f'{k}={v}\n' for k,v in config.items()))

    def invoke(self, *args):
        with contextlib.redirect_stdout(io.StringIO()):
            return lab.main(list(args))

    def fake_run(self, args, env=None, capture=False, timeout=60, required=True):
        if 'ps' in args:
            out = 'container-' + args[-1]
        elif 'inspect' in args:
            out = json.dumps({'Running': True, 'Health': {'Status': 'healthy'}})
        else:
            out = ''
        return subprocess.CompletedProcess(args, 0, out, '')

    def test_valid_config(self):
        self.assertEqual(len(lab.validate()['services']), 4)

    def test_verify_needs_no_docker_and_creates_no_env(self):
        with patch.object(lab, 'docker_ready', side_effect=AssertionError('不应访问 Docker')):
            self.assertEqual(self.invoke('verify'), 0)
        self.assertFalse((lab.INFRA / '.env').exists())

    def test_manifest_used_for_all_images(self):
        spec = lab.validate()
        self.assertEqual({s['image'] for s in spec['services'].values()}, {'${'+k+'}' for k in lab.IMAGE_KEYS})

    def test_floating_tag_rejected(self):
        path = lab.INFRA / 'versions.env'
        path.write_text(path.read_text().replace(lab.versions()['MYSQL_IMAGE'], 'mysql:latest'))
        with self.assertRaises(lab.LabError):
            lab.versions()

    def test_shell_expansion_rejected(self):
        self.write_config(MYSQL_PASSWORD='$(touch_bad)')
        with self.assertRaises(lab.LabError):
            lab.settings()

    def test_duplicate_key_rejected(self):
        path = lab.INFRA / 'versions.env'
        path.write_text(path.read_text() + 'MYSQL_IMAGE=' + lab.versions()['MYSQL_IMAGE'] + '\n')
        with self.assertRaises(lab.LabError):
            lab.versions()

    def test_unknown_key_rejected(self):
        self.write_config(MYSQL_IMAGE='mysql:8.0.0')
        with self.assertRaises(lab.LabError):
            lab.settings()

    def test_invalid_project_rejected(self):
        self.write_config(LAB_PROJECT_NAME='other-production-project')
        with self.assertRaises(lab.LabError):
            lab.settings()

    def test_duplicate_ports_rejected(self):
        self.write_config(REDIS_PORT='13306')
        with self.assertRaises(lab.LabError):
            lab.settings()

    def test_privileged_port_rejected(self):
        self.write_config(MYSQL_PORT='80')
        with self.assertRaises(lab.LabError):
            lab.settings()

    def test_root_user_rejected(self):
        self.write_config(MYSQL_USER='root')
        with self.assertRaises(lab.LabError):
            lab.settings()

    def test_env_init_never_overwrites(self):
        with contextlib.redirect_stdout(io.StringIO()):
            lab.settings(init=True)
        self.write_config(MYSQL_PORT='13307')
        self.assertEqual(lab.settings(init=True)[0]['MYSQL_PORT'], '13307')

    def test_env_file_mode_private(self):
        with contextlib.redirect_stdout(io.StringIO()):
            lab.settings(init=True)
        self.assertEqual((lab.INFRA / '.env').stat().st_mode & 0o777, 0o600)

    def test_shell_cannot_override_images_or_profiles(self):
        with patch.dict(os.environ, {'MYSQL_IMAGE':'mysql:latest', 'COMPOSE_PROFILES':'*'}):
            env = lab.docker_env(self.config)
        self.assertEqual(env['MYSQL_IMAGE'], lab.versions()['MYSQL_IMAGE'])
        self.assertNotIn('COMPOSE_PROFILES', env)

    def test_core_is_small(self):
        self.assertEqual(lab.selected([]), ['mysql','redis'])
        self.assertEqual(lab.selected(['kafka']), ['kafka'])
        self.assertEqual(lab.selected(['core','redis','kafka']), ['mysql','redis','kafka'])

    def test_unknown_profile_rejected(self):
        with self.assertRaises(lab.LabError):
            lab.selected(['all'])

    def test_reset_requires_exact_confirmation_before_docker(self):
        with patch.object(lab, 'docker_ready', side_effect=AssertionError('不应访问 Docker')):
            for args in [[], ['--yes'], ['--confirm-reset','other']]:
                with self.assertRaises(lab.LabError):
                    self.invoke('reset', *args)

    def test_down_keeps_volumes(self):
        with patch.object(lab, 'docker_ready', return_value=({}, '2.20.0')), patch.object(lab, 'run', side_effect=self.fake_run) as run:
            self.invoke('down')
        command = run.call_args.args[0]
        self.assertIn('down', command)
        self.assertNotIn('--volumes', command)
        self.assertNotIn('--rmi', command)
        self.assertNotIn('prune', command)

    def test_reset_only_exact_project(self):
        with patch.object(lab, 'docker_ready', return_value=({}, '2.20.0')), patch.object(lab, 'run', side_effect=self.fake_run) as run:
            self.invoke('reset', '--confirm-reset', self.config['LAB_PROJECT_NAME'])
        command = run.call_args.args[0]
        self.assertIn('--volumes', command)
        self.assertEqual(command[command.index('--project-name')+1], self.config['LAB_PROJECT_NAME'])

    def test_up_core_never_starts_all_profiles(self):
        with patch.object(lab, 'docker_ready', return_value=({}, '2.20.0')), patch.object(lab, 'run', side_effect=self.fake_run) as run:
            self.invoke('up')
        command = run.call_args_list[0].args[0]
        self.assertEqual(command[-2:], ['mysql','redis'])
        self.assertIn('--wait', command)
        self.assertEqual(command[command.index('--pull')+1], 'missing')

    def test_unhealthy_fails(self):
        def fail(args, *a, **kw):
            out = json.dumps({'Running':True, 'Health':{'Status':'unhealthy'}}) if 'inspect' in args else 'id'
            return subprocess.CompletedProcess(args,0,out,'')
        with patch.object(lab, 'run', side_effect=fail), contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(lab.LabError):
                lab.check_services(self.config, self.envpath, ['mysql'])

    def test_missing_container_fails(self):
        with patch.object(lab, 'run', return_value=subprocess.CompletedProcess([],0,'','')), contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(lab.LabError):
                lab.check_services(self.config, self.envpath, ['redis'])

    def test_stopped_container_fails_even_if_health_says_healthy(self):
        def stopped(args, *a, **kw):
            out = json.dumps({'Running':False, 'Health':{'Status':'healthy'}}) if 'inspect' in args else 'id'
            return subprocess.CompletedProcess(args,0,out,'')
        with patch.object(lab, 'run', side_effect=stopped), contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(lab.LabError):
                lab.check_services(self.config, self.envpath, ['mysql'])

    def test_build_keeps_wrapper_and_args_without_shell(self):
        with patch.object(lab, 'docker_ready', return_value=({}, '2.20.0')), patch.object(lab, 'run', side_effect=self.fake_run) as run:
            self.invoke('build', 'courses/示例课程', 'bash', './gradlew', '--no-daemon', 'test')
        cmd = run.call_args.args[0]
        self.assertEqual(cmd[-5:], ['java-build','bash','./gradlew','--no-daemon','test'])
        self.assertIn('--no-deps', cmd)
        self.assertIn('--rm', cmd)
        self.assertIn('/workspace/courses/示例课程', cmd)

    def test_build_cannot_escape_repo(self):
        with patch.object(lab, 'docker_ready', side_effect=AssertionError('不应访问 Docker')):
            with self.assertRaises(lab.LabError):
                self.invoke('build', '..', 'ls')

    def test_build_cannot_escape_by_symlink(self):
        (self.root / 'outside').symlink_to(self.root.parent, target_is_directory=True)
        with patch.object(lab, 'docker_ready', side_effect=AssertionError('不应访问 Docker')):
            with self.assertRaises(lab.LabError):
                self.invoke('build', 'outside', 'ls')

    def test_missing_docker_actionable(self):
        with patch.object(lab.shutil,'which',return_value=None):
            with self.assertRaisesRegex(lab.LabError,'未找到 Docker CLI'):
                lab.docker_ready(self.config)

    def test_old_compose_rejected(self):
        with patch.object(lab.shutil,'which',return_value='/mock/docker'), patch.object(lab,'run',return_value=subprocess.CompletedProcess([],0,'2.19.0','')):
            with self.assertRaisesRegex(lab.LabError,'Compose v2.20.0'):
                lab.docker_ready(self.config)

    def test_daemon_unavailable_actionable(self):
        results=[subprocess.CompletedProcess([],0,'2.20.0',''),subprocess.CompletedProcess([],1,'','拒绝访问')]
        with patch.object(lab.shutil,'which',return_value='/mock/docker'), patch.object(lab,'run',side_effect=results):
            with self.assertRaisesRegex(lab.LabError,'daemon 不可访问'):
                lab.docker_ready(self.config)

    def test_build_profile_uses_both_caches_without_socket(self):
        service = lab.validate()['services']['java-build']
        self.assertIn('maven-cache:/cache/maven', service['volumes'])
        self.assertIn('gradle-cache:/cache/gradle', service['volumes'])
        self.assertFalse(any('docker.sock' in v for v in service['volumes']))

    def test_old_engine_rejected_for_loopback_safety(self):
        results=[subprocess.CompletedProcess([],0,'2.20.0',''),subprocess.CompletedProcess([],0,json.dumps({'OSType':'linux','ServerVersion':'27.5.1'}),'')]
        with patch.object(lab.shutil,'which',return_value='/mock/docker'), patch.object(lab,'run',side_effect=results):
            with self.assertRaisesRegex(lab.LabError,'Docker Engine 28.0'):
                lab.docker_ready(self.config)

    def test_current_engine_and_compose_pass(self):
        info={'OSType':'linux','ServerVersion':'28.0.0','Architecture':'aarch64'}
        results=[subprocess.CompletedProcess([],0,'2.20.0',''),subprocess.CompletedProcess([],0,json.dumps(info),'')]
        with patch.object(lab.shutil,'which',return_value='/mock/docker'), patch.object(lab,'run',side_effect=results):
            self.assertEqual(lab.docker_ready(self.config), (info,'2.20.0'))

    def test_failed_up_never_deletes_data(self):
        def fail(args, *a, **kw):
            return subprocess.CompletedProcess(args,1 if 'up' in args else 0,'','')
        with patch.object(lab, 'docker_ready', return_value=({}, '2.20.0')), patch.object(lab, 'run', side_effect=fail) as run:
            with self.assertRaises(lab.LabError):
                self.invoke('up','kafka')
        self.assertFalse(any('down' in call.args[0] or 'prune' in call.args[0] for call in run.call_args_list))

if __name__ == '__main__':
    unittest.main(verbosity=2)
