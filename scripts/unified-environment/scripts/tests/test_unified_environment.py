"""无 Java/Docker daemon 的模拟回归；不等同于真实课程、容器或 Mac 验收。"""
import contextlib
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))
SPEC = importlib.util.spec_from_file_location('unified_lab', SCRIPTS / 'lab.py')
lab = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(lab)
SOURCE = lab.ROOT


class EnvironmentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='统一课程 fixture 空格-')
        self.root = Path(self.temp.name)
        self.addCleanup(self.temp.cleanup)
        for name in ('infra', 'shared'):
            shutil.copytree(SOURCE / name, self.root / name, ignore=shutil.ignore_patterns('.env'))
        (self.root / 'authoring').mkdir()
        shutil.copy(SOURCE / 'authoring/course-map.json', self.root / 'authoring/course-map.json')
        shutil.copy(SOURCE / 'gradle.properties', self.root / 'gradle.properties')
        (self.root / 'gradle/wrapper').mkdir(parents=True)
        shutil.copy(SOURCE / 'gradle/wrapper/gradle-wrapper.properties', self.root / 'gradle/wrapper/gradle-wrapper.properties')
        (self.root / 'scripts').mkdir()
        for name in ('gradle.sh', 'gradle_launcher.py'): shutil.copy(SOURCE / 'scripts' / name, self.root / 'scripts' / name)
        self.tasks = json.loads((self.root / 'authoring/course-map.json').read_text())['tasks']
        for task in self.tasks:
            destination = self.root / task['path']
            destination.mkdir(parents=True)
            if any((SOURCE / task['path'] / 'integration-test').rglob('*.java')):
                (destination / 'integration-test').mkdir()
                (destination / 'integration-test/Fixture.java').write_text('// static marker only\n')
        for relative in ('materials/backend-capstone/scripts/check.py', 'materials/backend-capstone/app/src/main/resources/static/index.html'):
            path = self.root / relative; path.parent.mkdir(parents=True, exist_ok=True); path.write_text('fixture')
        self.root_patch = patch.object(lab, 'ROOT', self.root)
        self.root_patch.start(); self.addCleanup(self.root_patch.stop)
        self.cfg, self.envpath = lab.config()

    def invoke(self, *args):
        with contextlib.redirect_stdout(io.StringIO()):
            return lab.main(list(args))

    def task(self, source, fragment):
        return next(t for t in self.tasks if t['source_course'] == source and fragment in t['source_task'])

    def change_config(self, **changes):
        cfg = dict(self.cfg); cfg.update(changes)
        (self.root / 'infra/.env').write_text(''.join(f'{k}={v}\n' for k, v in cfg.items()))

    def test_validate_entire_course_map(self):
        self.assertEqual(lab.validate(), self.tasks)
        self.assertTrue(all(lab.profile_for(task) in lab.PROFILES for task in self.tasks))

    def test_verify_never_runs_external_command(self):
        with patch.object(lab, 'execute', side_effect=AssertionError('必须离线')):
            self.assertEqual(self.invoke('verify'), 0)
        self.assertFalse((self.root / 'infra/.env').exists())

    def test_profiles_reads_every_task_from_single_map(self):
        with patch.object(lab, 'execute', side_effect=AssertionError('必须离线')):
            self.assertEqual(self.invoke('profiles'), 0)

    def test_config_rejects_shell_expansion(self):
        self.change_config(MYSQL_PASSWORD='$(touch_secret)')
        with self.assertRaises(lab.LabError): lab.config()

    def test_config_rejects_unknown_image_override(self):
        self.change_config(MYSQL_IMAGE='evil:1.0.0')
        with self.assertRaises(lab.LabError): lab.config()

    def test_duplicate_ports_rejected(self):
        self.change_config(CAPSTONE_HTTP_PORT=self.cfg['MYSQL_PORT'])
        with self.assertRaises(lab.LabError): lab.config()

    def test_auto_project_is_path_scoped(self):
        self.assertRegex(self.cfg['LAB_PROJECT_NAME'], r'^totalacademy-[a-f0-9]{12}$')
        with patch.object(lab, 'ROOT', Path('/different/course')):
            expected = 'totalacademy-' + hashlib.sha256(str(lab.ROOT).encode()).hexdigest()[:12]
        self.assertNotEqual(expected, self.cfg['LAB_PROJECT_NAME'])

    def test_init_is_private_and_does_not_overwrite(self):
        lab.config(init=True)
        path = self.root / 'infra/.env'
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        original = path.read_bytes(); lab.config(init=True)
        self.assertEqual(path.read_bytes(), original)

    def test_manifest_checksum_mismatch_is_fatal(self):
        path = self.root / 'shared/versions.env'
        path.write_text(path.read_text() + '\n# changed\n')
        with self.assertRaises(lab.LabError): lab.versions()

    def test_manifest_floating_tag_is_fatal(self):
        path = self.root / 'shared/versions.env'
        path.write_text(path.read_text().replace(lab.versions()['MYSQL_IMAGE'], 'mysql:latest'))
        with self.assertRaises(lab.LabError): lab.versions()

    def test_no_nested_version_truth_is_required(self):
        self.assertFalse((self.root / 'infra/versions.env').exists())
        self.assertFalse((self.root / 'materials/backend-capstone/shared/versions.env').exists())
        lab.validate()

    def test_host_env_cannot_override_versions_or_enable_profiles(self):
        with patch.dict(os.environ, {'MYSQL_IMAGE': 'evil:1.0.0', 'COMPOSE_PROFILES': '*', 'DOCKER_DEFAULT_PLATFORM': 'linux/amd64'}):
            env = lab.environment(self.cfg)
        self.assertEqual(env['MYSQL_IMAGE'], lab.versions()['MYSQL_IMAGE'])
        self.assertNotIn('COMPOSE_PROFILES', env)
        self.assertEqual(env['DOCKER_DEFAULT_PLATFORM'], 'linux/amd64')

    def test_capstone_uses_mapped_project_distribution(self):
        task = self.task('backend-capstone', '02-reliability')
        env = lab.environment(self.cfg, '02-reliability')
        self.assertEqual(Path(env['CAPSTONE_DIST_PATH']), self.root / task['path'] / 'build/install' / task['gradle_project'][1:])
        cmd = lab.compose(self.cfg, self.envpath, True)
        self.assertIn(self.cfg['LAB_PROJECT_NAME'] + '-capstone', cmd)

    def test_invalid_capstone_stage_rejected(self):
        with self.assertRaises(lab.LabError): lab.capstone_task('../../elsewhere')

    def test_map_path_traversal_rejected(self):
        path = self.root / 'authoring/course-map.json'; data = json.loads(path.read_text())
        data['tasks'][0]['path'] = '../outside'; path.write_text(json.dumps(data))
        with self.assertRaises(lab.LabError): lab.courses()

    def test_map_duplicate_module_rejected(self):
        path = self.root / 'authoring/course-map.json'; data = json.loads(path.read_text())
        data['tasks'][1]['gradle_project'] = data['tasks'][0]['gradle_project']; path.write_text(json.dumps(data))
        with self.assertRaises(lab.LabError): lab.courses()

    def test_ambiguous_task_shorthand_rejected(self):
        with self.assertRaises(lab.LabError): lab.task_for('practice')

    def test_db_check_keeps_full_test(self):
        for source in ('mysql-engineering', 'redis-engineering'):
            task = next(t for t in self.tasks if t['source_course'] == source)
            command = lab.check_plan(task)
            self.assertIn(task['gradle_project'] + ':test', command)
            self.assertFalse(any('unitTest' in word for word in command))

    def test_mq_check_forces_real_broker_gate(self):
        for task in self.tasks:
            if task['source_course'] == 'messaging': self.assertIn('-PwithDocker', lab.check_plan(task))

    def test_distributed_real_integration_never_downgraded(self):
        for leaf in ('05-idempotency', '06-transactions', '07-outbox-cache', '08-capacity'):
            task = self.task('distributed-systems', leaf)
            plan = lab.check_plan(task)
            self.assertIn(task['gradle_project'] + ':test', plan)
            if leaf in ('06-transactions', '07-outbox-cache'):
                self.assertNotIn(task['gradle_project'] + ':integrationTest', plan)
            else:
                self.assertIn(task['gradle_project'] + ':integrationTest', plan)

    def test_framework_and_capstone_integrations_kept(self):
        task = self.task('java-frameworks', '03-transactions')
        self.assertIn(task['gradle_project'] + ':integrationTest', lab.check_plan(task))
        for task in self.tasks:
            if task['source_course'] == 'backend-capstone': self.assertIn(task['gradle_project'] + ':integrationTest', lab.check_plan(task))

    def test_check_dry_run_has_no_external_effect(self):
        task = self.task('messaging', 'kafka/06-recovery')
        with patch.object(lab, 'execute', side_effect=AssertionError('只展示计划')):
            self.assertEqual(self.invoke('check', task['path'], '--dry-run'), 0)

    def test_check_preserves_nonzero_test_exit(self):
        task = next(t for t in self.tasks if lab.profile_for(t) == 'java')
        with patch.object(lab, 'jdk_ready'), patch.object(lab, 'execute', return_value=subprocess.CompletedProcess([], 7)) as run:
            self.assertEqual(self.invoke('check', task['path']), 7)
            self.assertIn(task['gradle_project'] + ':test', run.call_args.args[0])

    def test_check_requires_stop_before_redundant_containers(self):
        task = self.task('messaging', 'kafka/06-recovery')
        with patch.object(lab, 'jdk_ready'), patch.object(lab, 'docker_ready'), patch.object(lab, 'running_services', return_value=['mysql']), patch.object(lab, 'execute') as run:
            with self.assertRaises(lab.LabError): self.invoke('check', task['path'])
            run.assert_not_called()

    def test_conflict_does_not_auto_stop(self):
        with patch.object(lab, 'running_services', side_effect=[['mysql', 'kafka'], []]), patch.object(lab, 'execute') as run:
            with self.assertRaises(lab.LabError): lab.conflicts(self.cfg, self.envpath, {}, 'mysql')
            run.assert_not_called()

    def test_explicit_switch_only_stops_unneeded_owned_services(self):
        with patch.object(lab, 'running_services', side_effect=[['mysql', 'kafka'], []]), patch.object(lab, 'execute') as run:
            lab.conflicts(self.cfg, self.envpath, {}, 'mysql', True)
        command = run.call_args.args[0]
        self.assertEqual(command[-4:], ['stop', '--timeout', '30', 'kafka'])
        self.assertIn(self.cfg['LAB_PROJECT_NAME'], command)
        self.assertNotIn('--volumes', command)

    def test_occupied_port_never_kills_owner(self):
        with socket.socket() as listener:
            listener.bind(('127.0.0.1', 0)); port = listener.getsockname()[1]
            cfg = dict(self.cfg); cfg['MYSQL_PORT'] = str(port)
            with patch.object(lab, 'running_services', return_value=[]), patch.object(lab, 'execute') as run:
                with self.assertRaises(lab.LabError): lab.check_ports(cfg, [], {}, 'mysql')
                run.assert_not_called()

    def test_stop_is_scoped_and_preserves_volumes(self):
        with patch.object(lab, 'docker_ready', return_value=({}, '2.20.0')), patch.object(lab, 'execute', return_value=subprocess.CompletedProcess([], 0)) as run:
            self.assertEqual(self.invoke('stop', 'all'), 0)
        self.assertEqual(len(run.call_args_list), 2)
        for call in run.call_args_list:
            command = call.args[0]
            self.assertEqual(command[-3:], ['stop', '--timeout', '30'])
            self.assertNotIn('down', command); self.assertNotIn('--volumes', command); self.assertNotIn('prune', command)

    def test_start_mysql_only_selects_mysql(self):
        info = {'MemTotal': 4*1024**3}
        with patch.object(lab, 'docker_ready', return_value=(info, '2.20.0')), patch.object(lab, 'conflicts'), patch.object(lab, 'check_ports'), patch.object(lab, 'health'), patch.object(lab, 'execute') as run:
            self.assertEqual(self.invoke('start', 'mysql'), 0)
        command = run.call_args.args[0]
        self.assertEqual(command[-3:], ['--pull', 'missing', 'mysql'])
        self.assertNotIn('kafka', command); self.assertNotIn('rocketmq', command)

    def test_start_java_never_uses_docker(self):
        with patch.object(lab, 'jdk_ready'), patch.object(lab, 'docker_ready', side_effect=AssertionError('不应启动Docker')):
            self.assertEqual(self.invoke('start', 'java'), 0)

    def test_doctor_java_does_not_require_docker(self):
        with patch.object(lab, 'jdk_ready'), patch.object(lab, 'docker_ready', side_effect=AssertionError('java课不强制Docker')):
            self.assertEqual(self.invoke('doctor', 'java'), 0)

    def test_health_rejects_missing_or_unhealthy(self):
        with patch.object(lab, 'owned_ids', return_value=[]):
            with self.assertRaises(lab.LabError): lab.health([], {}, ['mysql'])
        with patch.object(lab, 'owned_ids', return_value=['owned']), patch.object(lab, 'execute', return_value=subprocess.CompletedProcess([], 0, '{"Running": true, "Health": {"Status": "unhealthy"}}')):
            with self.assertRaises(lab.LabError): lab.health([], {}, ['mysql'])

    def test_resources_stats_scopes_ids_and_df_is_read_only(self):
        with patch.object(lab, 'owned_ids', side_effect=[['course1'], ['course2']]), patch.object(lab, 'execute') as run:
            lab.resources(self.cfg, self.envpath, {})
        self.assertEqual(run.call_args_list[0].args[0], ['docker', 'stats', '--no-stream', 'course1', 'course2'])
        self.assertEqual(run.call_args_list[1].args[0], ['docker', 'system', 'df'])

    def test_architecture_override_warns_without_mutation(self):
        env = {'DOCKER_DEFAULT_PLATFORM': 'linux/amd64'}
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            lab.report_platform({'Architecture': 'aarch64', 'OSType': 'linux'}, env)
        self.assertIn('不匹配', output.getvalue())
        self.assertEqual(env['DOCKER_DEFAULT_PLATFORM'], 'linux/amd64')

    def test_capstone_fault_actions_require_explicit_target_and_service(self):
        for arguments in (('pause-service', 'mysql'), ('pause-service', 'capstone'), ('recover-service', 'java', '--service', 'mysql')):
            with patch.object(lab, 'docker_ready', side_effect=AssertionError('必须在外部操作前拒绝')):
                with self.assertRaises(lab.LabError): self.invoke(*arguments)

    def test_capstone_database_crash_is_rejected(self):
        with patch.object(lab, 'docker_ready', side_effect=AssertionError('不得接触Docker')):
            with self.assertRaises(lab.LabError): self.invoke('crash-service', 'capstone', '--service', 'mysql')

    def test_service_argument_cannot_change_other_actions(self):
        with self.assertRaises(lab.LabError): self.invoke('stop', 'capstone', '--service', 'mysql')

    def test_capstone_pause_is_project_and_service_scoped(self):
        with patch.object(lab, 'docker_ready', return_value=({}, '2.20.0')), patch.object(lab, 'owned_ids', return_value=['owned-mysql']), patch.object(lab, 'execute') as run:
            self.assertEqual(self.invoke('pause-service', 'capstone', '--service', 'mysql'), 0)
        command = run.call_args.args[0]
        self.assertIn(self.cfg['LAB_PROJECT_NAME'] + '-capstone', command)
        self.assertEqual(command[-4:], ['stop', '--timeout', '30', 'mysql'])
        self.assertNotIn('--volumes', command)

    def test_capstone_recover_restarts_same_container_not_default_stage(self):
        with patch.object(lab, 'docker_ready', return_value=({}, '2.20.0')), patch.object(lab, 'owned_ids', return_value=['stage02-delivery']), patch.object(lab, 'wait_existing_health') as waiting, patch.object(lab, 'execute') as run:
            self.assertEqual(self.invoke('recover-service', 'capstone', '--service', 'delivery'), 0)
        self.assertEqual(run.call_args.args[0], ['docker', 'start', 'stage02-delivery'])
        self.assertEqual(waiting.call_args.args[2:4], ('delivery', 'stage02-delivery'))

    def test_capstone_recover_refuses_absent_or_ambiguous_container(self):
        for ids in ([], ['one', 'two']):
            with patch.object(lab, 'owned_ids', return_value=ids), patch.object(lab, 'execute') as run:
                with self.assertRaises(lab.LabError): lab.operate_capstone_service('recover-service', [], {}, 'mysql', 30)
                run.assert_not_called()

    def test_capstone_application_crash_uses_explicit_signal(self):
        with patch.object(lab, 'docker_ready', return_value=({}, '2.20.0')), patch.object(lab, 'owned_ids', return_value=['owned-orders']), patch.object(lab, 'execute') as run:
            self.assertEqual(self.invoke('crash-service', 'capstone', '--service', 'orders'), 0)
        command = run.call_args.args[0]
        self.assertIn(self.cfg['LAB_PROJECT_NAME'] + '-capstone', command)
        self.assertEqual(command[-4:], ['kill', '--signal', 'SIGKILL', 'orders'])

    def test_recovery_wait_checks_real_health(self):
        response = subprocess.CompletedProcess([], 0, '{"Running":true,"Health":{"Status":"healthy"}}')
        with patch.object(lab, 'execute', return_value=response), patch.object(lab, 'health') as health:
            lab.wait_existing_health([], {}, 'mysql', 'owned', 30)
        health.assert_called_once_with([], {}, ['mysql'])

    def test_recovery_wait_fails_on_oom(self):
        response = subprocess.CompletedProcess([], 0, '{"Running":false,"OOMKilled":true}')
        with patch.object(lab, 'execute', return_value=response), patch.object(lab, 'time'):
            with self.assertRaises(lab.LabError): lab.wait_existing_health([], {}, 'mysql', 'owned', 30)

    def test_recovery_wait_is_bounded(self):
        response = subprocess.CompletedProcess([], 0, '{"Running":true,"Health":{"Status":"starting"}}')
        with patch.object(lab, 'execute', return_value=response), patch.object(lab.time, 'monotonic', side_effect=[0, 31]), patch.object(lab.time, 'sleep') as sleep:
            with self.assertRaises(lab.LabError): lab.wait_existing_health([], {}, 'mysql', 'owned', 30)
        sleep.assert_not_called()

    def test_stop_java_is_noop_and_never_touches_docker(self):
        for action in ('stop', 'status', 'logs'):
            with patch.object(lab, 'docker_ready', side_effect=AssertionError('不得访问Docker')), patch.object(lab, 'execute') as run:
                self.assertEqual(self.invoke(action, 'java'), 0)
                run.assert_not_called()

    def test_numeric_port_aliases_cannot_bypass_uniqueness(self):
        self.change_config(MYSQL_PORT='08088', CAPSTONE_HTTP_PORT='8088')
        with self.assertRaisesRegex(lab.LabError, '前导0'): lab.config()
        self.change_config(MYSQL_PORT='013306', CAPSTONE_HTTP_PORT='13306')
        with self.assertRaisesRegex(lab.LabError, '前导0'): lab.config()
        self.change_config(MYSQL_PORT='13306', CAPSTONE_HTTP_PORT='13306')
        with self.assertRaisesRegex(lab.LabError, '互不重复'): lab.config()

    def test_workbench_mismatched_actual_port_blocks_all_http_changes(self):
        self.change_config(CAPSTONE_HTTP_PORT='8089')
        binding = {'8080/tcp': [{'HostIp': '127.0.0.1', 'HostPort': '8088'}]}
        with patch.object(lab, 'docker_ready', return_value=({}, '2.20.0')), patch.object(lab, 'health'), patch.object(lab, 'owned_ids', return_value=['owned-old-port']), patch.object(lab, 'execute', return_value=subprocess.CompletedProcess([], 0, json.dumps(binding))) as run:
            with self.assertRaisesRegex(lab.LabError, '拒绝创建订单'): self.invoke('workbench-check', 'capstone')
        self.assertEqual(len(run.call_args_list), 1)
        self.assertEqual(run.call_args.args[0], ['docker', 'inspect', '--format', '{{json .NetworkSettings.Ports}}', 'owned-old-port'])
        self.assertFalse(any('check.py' in ' '.join(call.args[0]) for call in run.call_args_list))

    def test_workbench_requires_exact_loopback_binding(self):
        variants = (None, [], {}, {'8080/tcp': None}, {'8080/tcp': [{'HostIp': '0.0.0.0', 'HostPort': '8088'}]},
                    {'8080/tcp': [{'HostIp': '127.0.0.1', 'HostPort': '8088'}, {'HostIp': '0.0.0.0', 'HostPort': '8088'}]})
        for binding in variants:
            with patch.object(lab, 'owned_ids', return_value=['owned']), patch.object(lab, 'execute', return_value=subprocess.CompletedProcess([], 0, json.dumps(binding))):
                with self.assertRaises(lab.LabError): lab.verify_workbench_binding([], {'CAPSTONE_HTTP_PORT': '8088'})

    def test_workbench_requires_one_owned_orders_container(self):
        for ids in ([], ['first', 'second']):
            with patch.object(lab, 'owned_ids', return_value=ids), patch.object(lab, 'execute') as run:
                with self.assertRaises(lab.LabError): lab.verify_workbench_binding([], {'CAPSTONE_HTTP_PORT': '8088'})
                run.assert_not_called()

    def test_workbench_valid_binding_precedes_business_script(self):
        binding = {'8080/tcp': [{'HostIp': '127.0.0.1', 'HostPort': '8088'}]}
        responses = [subprocess.CompletedProcess([], 0, json.dumps(binding)),
                     subprocess.CompletedProcess([], 0, '{"Running":true,"Health":{"Status":"healthy"}}'),
                     subprocess.CompletedProcess([], 0)]
        with patch.object(lab, 'docker_ready', return_value=({}, '2.20.0')), patch.object(lab, 'health'), patch.object(lab, 'owned_ids', return_value=['owned-orders']), patch.object(lab, 'execute', side_effect=responses) as run:
            self.assertEqual(self.invoke('workbench-check', 'capstone'), 0)
        self.assertIn('{{json .NetworkSettings.Ports}}', run.call_args_list[0].args[0])
        self.assertIn('{{json .State}}', run.call_args_list[1].args[0])
        self.assertTrue(run.call_args_list[2].args[0][-1].endswith('/materials/backend-capstone/scripts/check.py'))

    def test_workbench_orders_stopping_after_binding_blocks_business(self):
        binding = {'8080/tcp': [{'HostIp': '127.0.0.1', 'HostPort': '8088'}]}
        responses = [subprocess.CompletedProcess([], 0, json.dumps(binding)), subprocess.CompletedProcess([], 0, '{"Running":false}')]
        with patch.object(lab, 'owned_ids', return_value=['owned']), patch.object(lab, 'execute', side_effect=responses):
            with self.assertRaisesRegex(lab.LabError, '拒绝发送业务请求'): lab.verify_workbench_binding([], {'CAPSTONE_HTTP_PORT': '8088'})

    def test_local_endpoint_allowlist_covers_desktop_rootless_and_loopback(self):
        for endpoint in ('unix:///var/run/docker.sock', 'unix:///run/user/1000/docker.sock',
                         'unix:///Users/learner/.docker/run/docker.sock', 'npipe:////./pipe/docker_engine',
                         'npipe:////./pipe/dockerDesktopLinuxEngine', 'tcp://127.0.0.1:2375', 'tcp://[::1]:2376'):
            lab.require_local_endpoint(endpoint, 'fixture')

    def test_remote_and_ambiguous_endpoints_are_rejected(self):
        for endpoint in ('ssh://user@host', 'tcp://192.0.2.1:2375', 'tcp://localhost:2375',
                         'tcp://127.0.0.2:2375', 'tcp://127.0.0.1.evil:2375',
                         'npipe:////server/pipe/docker_engine', 'npipe://server/pipe/docker_engine',
                         'unix://remote/var/run/docker.sock', 'unix://relative.sock', 'unix:relative.sock',
                         'unix:///tmp/socket?remote=host', 'unix:///tmp/socket?', 'unix:///tmp/socket#', 'unix:///tmp/%2fsocket',
                         'tcp://127.0.0.1:2375/other', 'tcp://127.0.0.1:2375#host',
                         'tcp://user@127.0.0.1:2375', 'tcp://127.0.0.1:0', 'tcp://127.0.0.1:65536',
                         'tcp://[::1', 'tcp://127.0.0.1', 'http://127.0.0.1:2375', '', None, [], ' tcp://127.0.0.1:2375'):
            with self.subTest(endpoint=endpoint), self.assertRaises(lab.LabError):
                lab.require_local_endpoint(endpoint, 'fixture')

    def test_remote_docker_host_is_rejected_even_with_local_context(self):
        env = {'DOCKER_HOST': 'tcp://192.0.2.1:2375', 'DOCKER_CONTEXT': 'desktop-linux'}
        with patch.object(lab, 'execute') as run:
            with self.assertRaisesRegex(lab.LabError, 'DOCKER_HOST'): lab.docker_ready(env)
            run.assert_not_called()
        self.assertEqual(env, {'DOCKER_HOST': 'tcp://192.0.2.1:2375', 'DOCKER_CONTEXT': 'desktop-linux'})

    def test_local_host_does_not_hide_remote_selected_context(self):
        env = {'DOCKER_HOST': 'unix:///var/run/docker.sock', 'DOCKER_CONTEXT': 'remote'}
        with patch.object(lab, 'execute', return_value=subprocess.CompletedProcess([], 0, '"ssh://user@host"')) as run:
            with self.assertRaisesRegex(lab.LabError, 'Docker context remote'): lab.docker_ready(env)
        self.assertEqual(len(run.call_args_list), 1)
        self.assertEqual(run.call_args.args[0][:3], ['docker', 'context', 'inspect'])

    def test_current_remote_context_is_rejected_before_daemon_or_compose(self):
        responses = [subprocess.CompletedProcess([], 0, 'production\n'), subprocess.CompletedProcess([], 0, '"tcp://192.0.2.1:2376"')]
        with patch.object(lab, 'execute', side_effect=responses) as run:
            with self.assertRaises(lab.LabError): lab.docker_ready({})
        self.assertEqual([c.args[0][:3] for c in run.call_args_list], [['docker', 'context', 'show'], ['docker', 'context', 'inspect']])

    def test_missing_or_malformed_context_endpoint_fails_closed(self):
        for raw in ('null', '""', '{}', '[]', 'not-json', '"unix://relative.sock"'):
            with self.subTest(raw=raw), patch.object(lab, 'execute', return_value=subprocess.CompletedProcess([], 0, raw)) as run:
                with self.assertRaises(lab.LabError): lab.docker_ready({'DOCKER_CONTEXT': 'default'})
                self.assertEqual(len(run.call_args_list), 1)
                self.assertEqual(run.call_args.args[0][:3], ['docker', 'context', 'inspect'])

    def test_unknown_context_name_is_rejected_before_inspect(self):
        for name in ('', '--help', 'bad name', 'default\nremote'):
            with patch.object(lab, 'execute', return_value=subprocess.CompletedProcess([], 0, name)) as run:
                with self.assertRaises(lab.LabError): lab.require_local_daemon({})
                self.assertEqual(len(run.call_args_list), 1)
                self.assertEqual(run.call_args.args[0], ['docker', 'context', 'show'])

    def test_local_context_gate_precedes_compose_and_info_without_mutation(self):
        env = {'DOCKER_HOST': 'unix:///run/user/1000/docker.sock', 'DOCKER_CONTEXT': 'rootless'}
        before = dict(env)
        responses = [subprocess.CompletedProcess([], 0, '"unix:///run/user/1000/docker.sock"'),
                     subprocess.CompletedProcess([], 0, '2.20.0'),
                     subprocess.CompletedProcess([], 0, '{"OSType":"linux","ServerVersion":"28.0.0"}')]
        with patch.object(lab, 'execute', side_effect=responses) as run:
            info, version = lab.docker_ready(env)
        self.assertEqual(version, '2.20.0'); self.assertEqual(env, before)
        self.assertEqual([c.args[0][:3] for c in run.call_args_list], [['docker', 'context', 'inspect'], ['docker', 'compose', 'version'], ['docker', 'info', '--format']])

    def test_default_desktop_context_is_resolved_read_only(self):
        responses = [subprocess.CompletedProcess([], 0, 'desktop-linux\n'),
                     subprocess.CompletedProcess([], 0, '"unix:///Users/test/.docker/run/docker.sock"')]
        with patch.object(lab, 'execute', side_effect=responses) as run:
            lab.require_local_daemon({})
        self.assertEqual(run.call_args_list[1].args[0][-1], 'desktop-linux')
        self.assertFalse(any('use' in call.args[0] for call in run.call_args_list))

    def test_container_check_never_reaches_gradle_with_remote_host(self):
        task = self.task('messaging', 'kafka/06-recovery')
        with patch.dict(os.environ, {'DOCKER_HOST': 'tcp://192.0.2.1:2375', 'DOCKER_CONTEXT': 'default'}), patch.object(lab, 'jdk_ready'), patch.object(lab, 'execute') as run:
            with self.assertRaises(lab.LabError): self.invoke('check', task['path'])
            run.assert_not_called()

    def test_mutating_actions_reject_remote_before_compose_or_http(self):
        cases = [('start', 'mysql'), ('stop', 'all'), ('pause-service', 'capstone', '--service', 'mysql'),
                 ('recover-service', 'capstone', '--service', 'orders'), ('crash-service', 'capstone', '--service', 'delivery'),
                 ('workbench-check', 'capstone')]
        for arguments in cases:
            with self.subTest(action=arguments), patch.dict(os.environ, {'DOCKER_HOST': 'ssh://remote'}), patch.object(lab, 'execute') as run:
                with self.assertRaises(lab.LabError): self.invoke(*arguments)
                run.assert_not_called()

    def test_official_distribution_needs_no_wrapper_files(self):
        self.assertFalse((self.root / 'gradlew').exists())
        self.assertFalse((self.root / 'gradlew.bat').exists())
        self.assertFalse((self.root / 'gradle/wrapper/gradle-wrapper.jar').exists())
        lab.validate()
        task = self.tasks[0]
        self.assertEqual(lab.check_plan(task)[1], str(self.root / 'scripts/gradle.sh'))

    def test_no_destructive_public_action(self):
        for action in ('reset', 'prune', 'down'):
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit): lab.parser().parse_args([action])


if __name__ == '__main__': unittest.main(verbosity=2)
