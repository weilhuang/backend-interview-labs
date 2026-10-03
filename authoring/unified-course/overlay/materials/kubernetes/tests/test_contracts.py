import copy,importlib.util,json,os,pathlib,sys,tempfile,unittest
from unittest.mock import patch,Mock
import yaml
ROOT=pathlib.Path(__file__).resolve().parents[1];COURSE=ROOT.parents[1];CANDIDATE=COURSE.parent
sys.path.insert(0,str(ROOT/'bin'));sys.path.insert(0,str(ROOT/'tests'))
import lab,check_task
TASK_ROOT=COURSE/'c11-cloud-native'
TASK_DIRS={'C11-04':TASK_ROOT/'04-kubernetes-basics/01-probes-and-replicas','C11-05':TASK_ROOT/'05-kubernetes-config/01-dns-config-secrets','C11-06':TASK_ROOT/'06-kubernetes-release/01-rollout-and-resources'}
RUN='123456abcdef';NS='c11-kind-'+RUN;IMAGE='c11-kind-api-'+RUN+':v1'

def docs():
    result=[]
    for p in sorted((ROOT/'manifests').glob('*.yaml')):
        text=p.read_text().replace('${APP_IMAGE}',IMAGE).replace('${REDIS_IMAGE}','redis:7.4.7-alpine3.21').replace('${NAMESPACE}',NS)
        result+=list(yaml.safe_load_all(text))
    return result

def flatten(values):
    return [obj for x in values for obj in (flatten(x['items']) if x.get('kind')=='List' else [x])]

class ManifestContracts(unittest.TestCase):
    def test_all_reference_yaml_pass(self):
        for task,d in TASK_DIRS.items():self.assertEqual([],check_task.errors(task,d/'answers'),task)
    def test_all_starters_fail_expected_contract(self):
        expected={'C11-04':'READINESSPROBE_ENDPOINT','C11-05':'SERVICE_SELECTOR','C11-06':'BOUNDED_ROLLOUT_STRATEGY'}
        for task,d in TASK_DIRS.items():self.assertIn(expected[task],check_task.errors(task,d))
    def test_rendered_reference_stays_scoped(self):
        rendered=lab.safe_documents(docs(),NS,RUN,{IMAGE,'redis:7.4.7-alpine3.21'})
        self.assertEqual(11,len(rendered))
        for obj in rendered:self.assertEqual(NS,obj['metadata']['namespace']);self.assertEqual(RUN,obj['metadata']['labels'][lab.LABEL])
    def test_reference_api_and_service_selector(self):
        rendered=lab.safe_documents(docs(),NS,RUN,{IMAGE,'redis:7.4.7-alpine3.21'})
        deployment=next(x for x in rendered if x['kind']=='Deployment' and x['metadata']['name']=='orders')
        service=next(x for x in rendered if x['kind']=='Service' and x['metadata']['name']=='orders')
        self.assertTrue(service['spec']['selector'].items()<=deployment['spec']['template']['metadata']['labels'].items())
    def rejection(self,mutate,reason):
        values=flatten(docs());mutate(values)
        with self.assertRaises(lab.LabError) as e:lab.safe_documents(values,NS,RUN,{IMAGE,'redis:7.4.7-alpine3.21'})
        self.assertEqual(reason,e.exception.reason)
    def deployment(self,values):return next(v for v in values if v['kind']=='Deployment' and v['metadata']['name']=='orders')
    def test_reject_external_namespace(self):self.rejection(lambda v:v[0]['metadata'].update(namespace='production'),'NAMESPACE_OVERRIDE')
    def test_reject_cluster_role(self):self.rejection(lambda v:v.append({'kind':'ClusterRole','metadata':{'name':'course-observer'}}),'KIND_NOT_ALLOWED')
    def test_reject_host_network(self):self.rejection(lambda v:self.deployment(v)['spec']['template']['spec'].update(hostNetwork=True),'HOST_ACCESS_FORBIDDEN')
    def test_reject_host_path(self):self.rejection(lambda v:self.deployment(v)['spec']['template']['spec']['volumes'].append({'name':'host','hostPath':{'path':'/'}}),'VOLUME_NOT_ALLOWED')
    def test_reject_token_automount(self):self.rejection(lambda v:self.deployment(v)['spec']['template']['spec'].update(automountServiceAccountToken=True),'TOKEN_MOUNT_FORBIDDEN')
    def test_reject_privileged(self):self.rejection(lambda v:self.deployment(v)['spec']['template']['spec']['containers'][0]['securityContext'].update(privileged=True),'CONTAINER_SECURITY_REQUIRED')
    def test_reject_unknown_image(self):self.rejection(lambda v:self.deployment(v)['spec']['template']['spec']['containers'][0].update(image='bad:latest'),'IMAGE_NOT_OWNED')
    def test_reject_unbounded_resources(self):self.rejection(lambda v:self.deployment(v)['spec']['template']['spec']['containers'][0]['resources']['limits'].update(memory='64Gi'),'RESOURCE_LIMIT_OUTSIDE_COURSE_BUDGET')
    def test_reject_public_service(self):self.rejection(lambda v:next(x for x in v if x['kind']=='Service')['spec'].update(type='LoadBalancer'),'PUBLIC_SERVICE_FORBIDDEN')
    def test_reject_rbac_secret_access(self):self.rejection(lambda v:next(x for x in v if x['kind']=='Role')['rules'][0]['resources'].append('secrets'),'RBAC_EXPANSION_FORBIDDEN')
    def test_reject_rbac_writes(self):self.rejection(lambda v:next(x for x in v if x['kind']=='Role')['rules'][0]['verbs'].append('create'),'RBAC_EXPANSION_FORBIDDEN')
    def test_reject_replicas_over_budget(self):self.rejection(lambda v:self.deployment(v)['spec'].update(replicas=100),'REPLICA_BUDGET')
    def test_redis_is_explicitly_ephemeral(self):
        redis=next(x for x in flatten(docs()) if x['kind']=='Deployment' and x['metadata']['name']=='redis')
        self.assertIn('emptyDir',redis['spec']['template']['spec']['volumes'][0])
    def test_configmap_does_not_contain_secret(self):
        cfg=yaml.safe_load((ROOT/'manifests/config.yaml').read_text());self.assertEqual({'redis-host','greeting','banner'},set(cfg['data']))
    def test_secrets_not_in_reference_manifest_files(self):
        for p in (ROOT/'manifests').glob('*.yaml'):
            for value in flatten(list(yaml.safe_load_all(p.read_text()))):self.assertNotEqual('Secret',value['kind'])

class EnvironmentGuardrails(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.runtime=pathlib.Path(self.temp.name)/'.runtime';self.runtime.mkdir(mode=0o700)
        self.patcher=patch.object(lab,'RUNTIME',self.runtime);self.patcher.start();self.l=lab.Lab()
        self.l.state={'run':RUN,'name':NS,'namespace':NS,'uids':{},'node_id':'node-identity','namespace_uid':'ns-identity'};self.l.save()
        self.cfg={'current-context':'kind-'+NS,'contexts':[{'name':'kind-'+NS,'context':{'cluster':'kind-'+NS,'user':'kind-'+NS}}],'clusters':[{'name':'kind-'+NS,'cluster':{'server':'https://127.0.0.1:12345'}}],'users':[{'name':'kind-'+NS,'user':{'client-key-data':'synthetic','client-certificate-data':'synthetic'}}]}
        self.writecfg()
    def writecfg(self):lab.dump(self.runtime/'kubeconfig',self.cfg)
    def tearDown(self):self.patcher.stop();self.temp.cleanup()
    def exec_mock(self,args,**kwargs):
        if args[:2]==['docker','inspect']:return Mock(stdout=json.dumps([{'Id':'node-identity','Config':{'Labels':{'io.x-k8s.kind.cluster':NS}}}]),returncode=0)
        self.assertIn('--kubeconfig',args);self.assertIn(str(self.runtime/'kubeconfig'),args);self.assertIn('--context',args);self.assertIn('kind-'+NS,args)
        return Mock(stdout=json.dumps({'metadata':{'uid':'ns-identity','labels':{lab.LABEL:RUN}}}),returncode=0)
    def test_valid_identity_passes_without_real_process(self):
        with patch.object(lab,'execute',side_effect=self.exec_mock):self.assertEqual(NS,self.l.guard()['name'])
    def test_foreign_context_stops_before_any_command(self):
        self.cfg['current-context']='production';self.writecfg()
        with patch.object(lab,'execute') as run,self.assertRaises(lab.LabError) as e:self.l.guard()
        run.assert_not_called();self.assertEqual('FOREIGN_CONTEXT',e.exception.reason)
    def test_remote_server_stops_before_any_command(self):
        self.cfg['clusters'][0]['cluster']['server']='https://prod.example:6443';self.writecfg()
        with patch.object(lab,'execute') as run,self.assertRaises(lab.LabError):self.l.guard()
        run.assert_not_called()
    def test_exec_credentials_rejected_before_command(self):
        self.cfg['users'][0]['user']['exec']={'command':'untrusted'};self.writecfg()
        with patch.object(lab,'execute') as run,self.assertRaises(lab.LabError):self.l.guard()
        run.assert_not_called()
    def test_unprotected_kubeconfig_rejected(self):
        (self.runtime/'kubeconfig').chmod(0o644)
        with patch.object(lab,'execute') as run,self.assertRaises(lab.LabError):self.l.guard()
        run.assert_not_called()
    def test_namespace_uid_mismatch_rejected(self):
        def altered(args,**kwargs):
            r=self.exec_mock(args,**kwargs)
            if args[0]=='kubectl':r.stdout=json.dumps({'metadata':{'uid':'foreign','labels':{lab.LABEL:RUN}}})
            return r
        with patch.object(lab,'execute',side_effect=altered),self.assertRaises(lab.LabError) as e:self.l.guard()
        self.assertEqual('NAMESPACE_OWNERSHIP_MISMATCH',e.exception.reason)
    def test_missing_docker_is_invalid_environment(self):
        with patch.object(lab.shutil,'which',return_value=None),patch.object(lab,'execute') as run,self.assertRaises(lab.LabError) as e:lab.preflight({})
        self.assertEqual('INVALID_ENV',e.exception.status);self.assertEqual('MISSING_DOCKER',e.exception.reason);run.assert_not_called()
    def test_resource_uid_substitution_rejected(self):
        self.l.state['uids']['deployment/orders']='original';self.l.save()
        obj={'metadata':{'uid':'replacement','labels':{lab.LABEL:RUN}}}
        with patch.object(self.l,'guard',return_value=self.l.state),patch.object(self.l,'get',return_value=obj),self.assertRaises(lab.LabError) as e:self.l.own('deployment','orders')
        self.assertEqual('RESOURCE_UID_CHANGED',e.exception.reason)
    def test_command_failure_never_passes_as_expected_negative(self):
        with patch.object(lab.subprocess,'run',return_value=Mock(returncode=1,stdout='',stderr='synthetic detail')),self.assertRaises(lab.LabError) as e:lab.execute(['mock'])
        self.assertEqual('INVALID_ENV',e.exception.status)
    def test_http_transport_without_status_is_invalid(self):
        with patch.object(self.l,'exec_java',return_value=Mock(stdout='',returncode=3)),self.assertRaises(lab.LabError) as e:self.l.call(allow_failure=True)
        self.assertEqual('INVALID_ENV',e.exception.status);self.assertEqual('HTTP_TRANSPORT_NO_WITNESS',e.exception.reason)
    def test_http_503_is_real_response_witness(self):
        with patch.object(self.l,'exec_java',return_value=Mock(stdout='{"status":503,"body":{"status":"DOWN"}}',returncode=1)):
            self.assertEqual(503,self.l.call(allow_failure=True)['status'])
    def test_timeout_is_not_business_negative(self):
        import subprocess
        with patch.object(lab.subprocess,'run',side_effect=subprocess.TimeoutExpired(['mock'],1)),self.assertRaises(lab.LabError) as e:lab.execute(['mock'])
        self.assertEqual('INVALID_ENV',e.exception.status)
    def test_bootstrap_can_wait_for_initial_http_listener(self):
        with patch.object(self.l,'call',side_effect=[lab.LabError('INVALID_ENV','HTTP_TRANSPORT_NO_WITNESS'),{'status':503},{'status':200}]),patch.object(lab.time,'sleep'):
            self.assertTrue(self.l.wait_startup('pod',seconds=1)['startup_http_503_observed'])
    def test_bootstrap_no_http_is_invalid_env_not_negative_pass(self):
        with patch.object(self.l,'call',side_effect=lab.LabError('INVALID_ENV','HTTP_TRANSPORT_NO_WITNESS')),patch.object(lab.time,'sleep'),patch.object(lab.time,'monotonic',side_effect=[0,0.1,2]),self.assertRaises(lab.LabError) as e:self.l.wait_startup('pod',seconds=1)
        self.assertEqual('INVALID_ENV',e.exception.status)
    def test_bootstrap_sustained_503_is_contract_failure(self):
        with patch.object(self.l,'call',return_value={'status':503}),patch.object(lab.time,'sleep'),patch.object(lab.time,'monotonic',side_effect=[0,0.1,2]),self.assertRaises(lab.LabError) as e:self.l.wait_startup('pod',seconds=1)
        self.assertEqual('FAIL',e.exception.status)
    def test_bootstrap_identity_error_is_never_suppressed(self):
        with patch.object(self.l,'call',side_effect=lab.LabError('INVALID_ENV','NAMESPACE_OWNERSHIP_MISMATCH')),self.assertRaises(lab.LabError) as e:self.l.wait_startup('pod')
        self.assertEqual('NAMESPACE_OWNERSHIP_MISMATCH',e.exception.reason)
    def test_does_not_remove_unverified_cluster(self):
        with patch.object(self.l,'guard',side_effect=lab.LabError('INVALID_ENV','BAD_CONTEXT')),patch.object(lab,'execute') as run,self.assertRaises(lab.LabError):self.l.down()
        run.assert_not_called()

class SourcesAndMetadata(unittest.TestCase):
    def test_no_nested_course_root_in_shared_or_tasks(self):
        self.assertEqual([],list(ROOT.rglob('course-info.yaml')))
        self.assertEqual([],list(TASK_ROOT.rglob('course-info.yaml')))
    def test_answers_match_shared_sources(self):
        for code,d in TASK_DIRS.items():
            for source,target in lab.TASKS[code].items():self.assertEqual((ROOT/target).read_bytes(),(d/'answers'/source).read_bytes())
    def test_java_no_secret_in_info_or_to_string(self):
        source=(ROOT/'src/labs/KubernetesApp.java').read_text();branch=source.split('path.equals("/info")',1)[1].split('return;',1)[0]
        self.assertNotIn('redisPassword',branch);self.assertIn('AppConfig[redacted]',(ROOT/'src/labs/AppConfig.java').read_text())
    def test_docker_two_global_args(self):
        text=(ROOT/'Dockerfile').read_text();self.assertIn('ARG JAVA_RUNTIME_IMAGE',text.split('FROM',1)[0]);self.assertIn('USER 10001:10001',text)
    def test_no_global_destructive_command(self):
        text=(ROOT/'bin/lab.py').read_text();self.assertNotIn("'prune'",text);self.assertNotIn("'--all'",text);self.assertNotIn("'--all-namespaces'",text)
    def test_junit_bridge_all_visible_and_paths_explicit(self):
        for d in TASK_DIRS.values():
            text=(d/'test/LabCheckTest.java').read_text();self.assertIn('course.taskDir',text);self.assertIn('course.materialsDir',text);self.assertNotIn('user.dir',text)
if __name__=='__main__':unittest.main()
