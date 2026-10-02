import concurrent.futures,json,os,pathlib,signal,socket,subprocess,sys,tempfile,time,unittest
from fake_redis import State,FakeRedis
ROOT=pathlib.Path(__file__).resolve().parents[1]
PAYLOAD=ROOT.parents[1]

class ConfigurationTests(unittest.TestCase):
    def setUp(self):self.compose=json.loads((PAYLOAD/'infra/cloudnative.compose.yaml').read_text())
    def test_no_hostwide_or_management_exposure(self):
        self.assertNotIn('name',self.compose)
        for name,service in self.compose['services'].items():
            self.assertNotIn('container_name',service);self.assertNotIn('privileged',service)
            self.assertNotIn('network_mode',service)
            for port in service.get('ports',[]):self.assertTrue(port.startswith('127.0.0.1:'),port)
        self.assertNotIn('ports',self.compose['services']['redis'])
    def test_resource_and_log_bounds(self):
        for service in self.compose['services'].values():
            for key in ['mem_limit','cpus','pids_limit']:self.assertIn(key,service)
            self.assertEqual(service['logging']['options']['max-file'],'3')
    def test_volumes_are_project_scoped(self):
        self.assertEqual(self.compose['volumes'],{'cloudnative-redis-data':{}})
        self.assertEqual(self.compose['services']['redis']['volumes'],['cloudnative-redis-data:/data'])
    def test_real_health_and_exec_entry(self):
        api=self.compose['services']['cloudnative-api']
        self.assertEqual(api['healthcheck']['test'][-2:],['probe','ready'])
        self.assertEqual(api['depends_on']['redis']['condition'],'service_healthy')
        source=(ROOT/'container/Dockerfile').read_text()
        self.assertIn('USER 10001:10001',source)
        self.assertIn('FROM ${JAVA_RUNTIME_IMAGE}',source)
        self.assertNotIn('COPY . ',source)
        self.assertNotIn(':latest',source)
        self.assertIn('ENTRYPOINT ["java"',source)
    def test_build_context_excludes_fake_secret_and_tests(self):
        # Allowlist是实际文件规则契约；Docker自身的解析仍归真实镜像阶段验收。
        rules=(ROOT/'.dockerignore').read_text().splitlines()
        self.assertEqual(rules[0],'*');self.assertNotIn('!.env',rules)
        self.assertNotIn('!tests/**',rules);self.assertNotIn('!answers/**',rules)
        self.assertNotIn('!wrong/**',rules)

class ReferenceModelTests(unittest.TestCase):
    """判题断言/假服务自测，不计Java或真实Redis业务通过数。"""
    def setUp(self):self.state=State();self.key='c11-fixture:inventory'
    def seed(self):return self.state.apply(['EVAL','academy:c11:seed:v1','1',self.key])
    def reserve(self,id,qty):return self.state.apply(['EVAL','academy:c11:reserve:v1','1',self.key,id,str(qty)])
    def test_seed_after_order_does_not_refill(self):
        self.assertEqual(self.seed(),1);self.assertEqual(self.reserve('one',2),'CREATED|8')
        self.assertEqual(self.seed(),0);self.assertEqual(self.state.data[self.key]['stock'],'8')
    def test_repeat_payload_conflict_and_no_double_charge(self):
        self.seed();self.reserve('one',2)
        self.assertEqual(self.reserve('one',2),'REPLAY|8')
        self.assertEqual(self.reserve('one',3),'CONFLICT')
        self.assertEqual(self.state.data[self.key]['stock'],'8')
    def test_reference_rejects_overselling_under_concurrency(self):
        self.seed()
        with concurrent.futures.ThreadPoolExecutor(max_workers=16) as pool:r=list(pool.map(lambda i:self.reserve(str(i),1),range(32)))
        self.assertEqual(sum(x.startswith('CREATED|') for x in r),10)
        self.assertEqual(r.count('SOLD_OUT'),22)
    def test_protocol_server_auth_and_ping(self):
        server=FakeRedis().start()
        try:
            with socket.create_connection(('127.0.0.1',server.port),timeout=2) as s:
                s.sendall(b'*1\r\n$4\r\nPING\r\n');self.assertTrue(s.recv(1024).startswith(b'-NOAUTH'))
                password=server.state.password.encode();s.sendall(b'*2\r\n$4\r\nAUTH\r\n$'+str(len(password)).encode()+b'\r\n'+password+b'\r\n')
                self.assertEqual(s.recv(1024),b'+OK\r\n')
                s.sendall(b'*1\r\n$4\r\nPING\r\n');self.assertEqual(s.recv(1024),b'$4\r\nPONG\r\n')
        finally:server.close()

class SignalTests(unittest.TestCase):
    def run_entrypoint(self,entry,expected):
        with tempfile.TemporaryDirectory(prefix='c11-signal-') as d:
            path=pathlib.Path(d);ready=path/'ready';done=path/'done';fixture=path/'child.py'
            fixture.write_text('import os,signal,time,pathlib\n'
                'def stop(s,f):\n pathlib.Path(os.environ["DONE"]).write_text("drained");raise SystemExit(0)\n'
                'signal.signal(signal.SIGTERM,stop)\npathlib.Path(os.environ["READY"]).write_text("ready")\n'
                'while True:time.sleep(.05)\n')
            stub=path/'java';stub.write_text('#!/bin/sh\nexec "'+sys.executable+'" "'+str(fixture)+'"\n');stub.chmod(0o755)
            env=dict(os.environ,PATH=str(path)+':'+os.environ['PATH'],READY=str(ready),DONE=str(done))
            process=subprocess.Popen(['sh',str(entry)],env=env,start_new_session=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
            try:
                deadline=time.monotonic()+3
                while not ready.exists():
                    self.assertIsNone(process.poll());self.assertLess(time.monotonic(),deadline);time.sleep(.02)
                process.send_signal(signal.SIGTERM)
                try:process.wait(timeout=.8);terminated=True
                except subprocess.TimeoutExpired:terminated=False
                self.assertEqual(terminated,expected)
                self.assertEqual(done.exists(),expected)
            finally:
                # 仅回收本测试用start_new_session创建的进程组，不接触Docker/其他进程。
                if process.poll() is None:os.killpg(process.pid,signal.SIGKILL)
                process.communicate(timeout=2)
    def test_exec_forwards_term_to_real_child(self):self.run_entrypoint(ROOT/'container/entrypoint.sh',True)
    def test_wrong_shell_is_killed_by_signal_assertion(self):self.run_entrypoint(ROOT/'wrong/entrypoint-swallow-term.sh',False)


class DockerScopeTests(unittest.TestCase):
    def test_reject_unknown_project_before_any_subprocess(self):
        from docker_verify import validate_context,InvalidEnvironment
        with self.assertRaises(InvalidEnvironment):validate_context(['docker','compose','--project-name','production'],{},'http://127.0.0.1:18085')
    def test_reject_learner_namespace_for_destructive_business_fixture(self):
        from docker_verify import validate_context,InvalidEnvironment
        with self.assertRaises(InvalidEnvironment):validate_context(['docker','compose','--project-name','totalacademy-123-c11-01-verify-abcdef12'],{'CLOUDNATIVE_NAMESPACE':'c11-demo','CLOUDNATIVE_HTTP_PORT':'18085'},'http://127.0.0.1:18085')
    def test_accept_only_bounded_loopback_verify_context(self):
        from docker_verify import validate_context
        self.assertEqual(validate_context(['docker','compose','--project-name','totalacademy-123-c11-01-verify-abcdef12','-f',str(PAYLOAD/'infra/cloudnative.compose.yaml')],{'LAB_PROJECT_NAME':'totalacademy-123-c11-01-verify-abcdef12','CLOUDNATIVE_NAMESPACE':'c11-verify-1234567890abcdef','CLOUDNATIVE_HTTP_PORT':'18085'},'http://127.0.0.1:18085'),'totalacademy-123-c11-01-verify-abcdef12')


class UnsafeMutationTests(unittest.TestCase):
    def setUp(self):
        self.data=json.loads((PAYLOAD/'infra/cloudnative.compose.yaml').read_text())
    def test_reference_compose_policy(self):
        from compose_policy import validate_compose
        self.assertEqual(validate_compose(self.data),[])
    def test_wrong_all_interfaces_rejected_without_launch(self):
        from compose_policy import validate_compose
        self.data['services']['cloudnative-api']['ports']=['0.0.0.0:18085:8080']
        self.assertIn('cloudnative-api:NON_LOOPBACK_PORT',validate_compose(self.data))
    def test_wrong_shared_volume_rejected_without_launch(self):
        from compose_policy import validate_compose
        self.data['volumes']['cloudnative-redis-data']={'name':'everyone-shares-this'}
        self.assertIn('cloudnative-redis-data:EXTERNAL_OR_FIXED_VOLUME_NAME',validate_compose(self.data))
    def test_wrong_latest_rejected_without_pull(self):
        from compose_policy import validate_compose
        self.data['services']['redis']['image']='redis:latest'
        self.assertIn('redis:BYPASS_VERSION_LEDGER',validate_compose(self.data))


class DockerHarnessTests(unittest.TestCase):
    def setup_context(self):
        return (['docker','compose','--project-name','totalacademy-unit-c11-01-verify-abcdef12','-f',str(PAYLOAD/'infra/cloudnative.compose.yaml')],
                {'LAB_PROJECT_NAME':'totalacademy-unit-c11-01-verify-abcdef12','CLOUDNATIVE_NAMESPACE':'c11-verify-1234567890abcdef','CLOUDNATIVE_HTTP_PORT':'18085','REDIS_PASSWORD':'synthetic-password-only'},
                'http://127.0.0.1:18085')
    def test_missing_docker_is_not_run_not_green(self):
        from unittest.mock import patch
        from docker_verify import run_verification
        with tempfile.TemporaryDirectory() as d,patch('docker_verify.subprocess.run',side_effect=FileNotFoundError):
            result=run_verification(*self.setup_context(),d)
            self.assertEqual(result['status'],'NOT_RUN')
            self.assertEqual(json.loads((pathlib.Path(d)/'docker-report.json').read_text())['status'],'NOT_RUN')
    def test_daemon_denied_is_not_run_without_fallback(self):
        from unittest.mock import patch
        from docker_verify import run_verification
        denied=subprocess.CompletedProcess(['docker','info'],1,'','permission denied')
        with tempfile.TemporaryDirectory() as d,patch('docker_verify.subprocess.run',return_value=denied) as run:
            result=run_verification(*self.setup_context(),d)
            self.assertEqual(result['status'],'NOT_RUN');self.assertEqual(run.call_count,1)
    def test_partial_up_failure_stops_only_owned_project(self):
        from unittest.mock import patch
        from docker_verify import run_verification
        calls=[]
        def run(argv,**kwargs):
            calls.append(argv)
            return subprocess.CompletedProcess(argv,1 if 'up' in argv else 0,'27.0.0\n' if 'info' in argv else '','synthetic build error' if 'up' in argv else '')
        with tempfile.TemporaryDirectory() as d,patch('docker_verify.subprocess.run',side_effect=run):
            with self.assertRaises(RuntimeError):run_verification(*self.setup_context(),d)
            self.assertTrue(any(command[-1]=='stop' for command in calls))
            self.assertFalse(any('prune' in command or '--volumes' in command for command in calls))
            self.assertEqual(json.loads((pathlib.Path(d)/'docker-report.json').read_text())['status'],'FAIL')


class VariantHarnessTests(unittest.TestCase):
    def test_wrong_seed_mutation_removes_guard_not_entire_script(self):
        from docker_variant_verify import make_context
        with tempfile.TemporaryDirectory() as d:
            path=make_context(pathlib.Path(d)/'context','wrong-seed-reset')
            source=(path/'src/labs/Inventory.java').read_text()
            self.assertNotIn("if redis.call('EXISTS', KEYS[1])",source)
            self.assertIn("'stock', '10'",source)
    def test_right_context_keeps_fake_secret_out_of_allowlist(self):
        from docker_variant_verify import make_context
        with tempfile.TemporaryDirectory() as d:
            path=make_context(pathlib.Path(d)/'context','reference-exec')
            self.assertTrue((path/'.env').exists());self.assertNotIn('!.env',(path/'.dockerignore').read_text())
    def test_build_failure_is_not_accepted_as_wrong_solution_killed(self):
        from docker_variant_verify import expected_semantic_failure
        self.assertFalse(expected_semantic_failure('wrong-seed-reset',AssertionError('Docker command failed'),{'cases':[]},[]))
        self.assertFalse(expected_semantic_failure('wrong-ready',AssertionError('Connection refused'),{'cases':[]},[]))
    def test_case_id_without_payload_and_health_witness_is_rejected(self):
        from docker_variant_verify import expected_semantic_failure
        from verification_guard import ContractViolation
        self.assertFalse(expected_semantic_failure('wrong-ready',ContractViolation('ready_rejects_unseeded',{'status':200}),{'cases':[]},[]))

if __name__=='__main__':unittest.main(verbosity=2)
