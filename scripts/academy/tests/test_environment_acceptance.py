"""Synthetic negative fixtures only. These never claim real Docker/native acceptance."""
import copy,json,os,stat,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from gates import GateError,sha,dump
from environment_contract import PROFILES,COMMON,CAPSTONE,expected_checks,validate_environment
from native_handoff import pack,unpack,json_bytes
from release_gate import evaluate
from run_environment import Acceptance
import test_gates as legacy_fixtures
from test_gates import fixture,contract as report_contract
from gates import validate_report


def native_fixture(archive_hash='a'*64, archive_size=42):
    value={'status':'PASS','phase':'full-validation','native_archive_verified':True,'native_tests':'PASS','repository':'owner/repo','commit':'b'*40,'run_id':'123','run_attempt':'1',
           'stages':{key:{'status':'PASS'} for key in ('archive','student_import','educator_import','gradle_jvm')}}
    value['stages']['archive'].update(archive_sha256=archive_hash,bytes=archive_size)
    source=report_contract()
    value['stages']['source_contract']={'status':'PASS','counts':source['counts'],'sha256':'c'*64,
        'tasks':[{'path':row['path'],'expected_link_urls':row['expected_link_urls']} for row in source['tasks']]}
    value['stages']['native_validation']=validate_report(fixture(),source)
    for key in ('official_export_process','official_validate_process'):value['stages'][key]={'exit_code':0,'timed_out':False,'disk_low':False}
    return value


def evidence_fixture():
    native=native_fixture();identity={key:native[key] for key in ('repository','commit','run_id','run_attempt')}
    identity.update(archive_sha256='a'*64,contract_sha256='c'*64,handoff_sha256='d'*64,image_ledger_sha256='e'*64)
    report={'schema_version':1,**identity,'status':'PASS','runtime':'real-docker','course_origin':'official-import-snapshot','docker_api_version':'1.44','learner_business_checks':'NOT_RUN_EXPECTED_STARTER','python_executable':'/opt/python/bin/python3.12','repo_root':'/repo','run_root':'/run','mysql_database':'interview_lab','ports':{'MYSQL_PORT':'13306','REDIS_PORT':'16379','KAFKA_PORT':'19092','ROCKETMQ_PORT':'18081','CAPSTONE_HTTP_PORT':'8088'},
        'checks':{},'commands':[],'imports':{mode:{'status':'PASS','files':963,'post_runtime_revalidated':True} for mode in ('student','educator')},
        'image_ledger':{key:'fixture:'+key for key in ('MYSQL_IMAGE','REDIS_IMAGE','KAFKA_IMAGE','ROCKETMQ_IMAGE','JAVA_BUILD_IMAGE','TESTCONTAINERS_RYUK_IMAGE','TESTCONTAINERS_TINY_IMAGE')},
        'ownership':{'projects':['totalacademy-ci-123-1','totalacademy-ci-123-1-capstone'],'empty_before':True,'empty_after':True,'containers':{'fixture':'fixture'},'volumes':{'fixture':'fixture'}}}
    def lab(action,profile,*extra):return ['bash','/run/handoff/educator/scripts/lab.sh',action,profile,*extra]
    inspect_command=['docker','inspect','--format','{"id":{{json .Id}},fixture}', 'a'*64]
    external='/run/gradle-home/caches/fixture.jar';classpath='/run/probe-classes:'+external
    def add(name,argvs,observations=None):
        ids=[]
        for argv in argvs:
            identifier=len(report['commands'])+1;ids.append(identifier)
            report['commands'].append({'id':identifier,'argv':argv,'exit_code':0,'timed_out':False,'timeout_seconds':90,'seconds':1,'stdout_sha256':'f'*64,'stderr_sha256':'f'*64})
        report['checks'][name]={'status':'PASS','command_ids':ids,'observations':observations or {'synthetic_fixture':True}}
    for profile in PROFILES:
        for step,action in [('start','start'),('doctor','doctor'),('health','health'),('stop','stop')]+([] if profile=='capstone' else [('restart','start'),('stop_final','stop')]):add(profile+'.'+step,[lab(action,profile,*(['--stage','05-defense'] if profile=='capstone' and action=='start' else []))])
        add(profile+'.bindings',[inspect_command],{'actual_loopback_only':True,'container_ids':['id']})
        add(profile+'.preserved',[inspect_command],{'same_volume_ids':True})
        if profile=='capstone':continue
        for step,read in [('write_read',False),('read_after_restart',True)]:
            if profile=='redis':argv=[report['python_executable'],'/repo/scripts/academy/redis_probe.py','--port','16379','--marker','totalacademy-ci-123-1']+(['--read-only'] if read else [])
            elif profile=='rocketmq':argv=['java','-Xmx256m','-XX:MaxDirectMemorySize=64m','-cp',classpath,'lab.environment.RocketSmoke','read' if read else 'write','127.0.0.1:18081','lab_ci_roundtrip','lab_ci_roundtrip_group','lab_ci_durable','lab_ci_durable_group','totalacademy-ci-123-1']
            else:argv=['java','-Xmx256m','-cp',classpath,'lab.environment.ServiceSmoke',profile+('-read' if read else '-write'),'127.0.0.1:'+('13306' if profile=='mysql' else '19092'),'interview_lab','totalacademy-ci-123-1']
            add(profile+'.'+step,[argv])
    add('preflight',[['docker','version','--format','{{json .}}']])
    for mode in ('student','educator'):add('learner_entry' if mode=='student' else 'educator_entry',[['bash','/run/handoff/'+mode+'/scripts/lab.sh','verify']])
    add('launcher_prepare',[['bash','/run/handoff/educator/scripts/gradle.sh','prepare','--download']])
    add('launcher_verify',[['bash','/run/handoff/educator/scripts/gradle.sh','--version']])
    add('probe_compile',[['javac','--release','21','-cp',external,'-d','/run/probe-classes','/repo/scripts/academy/probes/RocketSmoke.java','/repo/scripts/academy/probes/ServiceSmoke.java'],['bash','/run/handoff/educator/scripts/gradle.sh','--no-daemon','--max-workers=1','--console=plain','-PdockerApiVersion=1.44','-I','/repo/scripts/academy/probes/classpath.gradle',':messaging-support:academyEnvironmentClasspath']])
    add('import_integrity',[['bash','/run/handoff/'+mode+'/scripts/lab.sh','verify'] for mode in ('student','educator')])
    add('capstone.http',[lab('workbench-check','capstone')])
    add('capstone.browser',[['node','/run/handoff/educator/materials/backend-capstone/scripts/browser-smoke.mjs']],{'viewports':[320,390,800,801,1440]})
    add('capstone.pause',[lab('pause-service','capstone','--service',service) for service in ('orders','delivery')])
    add('capstone.unavailable',[[report['python_executable'],'/repo/scripts/academy/http_probe.py','--port','8088','--path','/api/replay','--status','503','--json','{}']])
    add('capstone.recover',[lab('recover-service','capstone','--service','delivery')])
    add('capstone.replay',[[report['python_executable'],'/repo/scripts/academy/http_probe.py','--port','8088','--path','/api/orders/recover-123-1/cancel','--status','200','--json','{}']])
    add('capstone.same_stage',[inspect_command],{'stage':'05-defense','same_container_ids':True,'same_mounts':True})
    add('cleanup',[['docker',kind,'rm','fixture'] for kind in ('container','volume','network')])
    return report,native,identity

class EnvironmentContractTests(unittest.TestCase):
    def test_complete_synthetic_schema_passes_only_parser(self):
        report,native,identity=evidence_fixture();self.assertEqual(validate_environment(report,native,identity)['status'],'PASS');
        with self.assertRaises(GateError):evaluate(native,report,identity)
    def reject(self,change):
        report,native,identity=evidence_fixture();change(report,native,identity)
        with self.assertRaises((GateError,KeyError,TypeError)):validate_environment(report,native,identity)
    def test_missing_every_required_check_rejected(self):
        for name in expected_checks():
            with self.subTest(name=name):self.reject(lambda r,n,i:r['checks'].pop(name))
    def test_skipped_every_required_check_rejected(self):
        for name in expected_checks():
            with self.subTest(name=name):self.reject(lambda r,n,i:r['checks'][name].update(status='SKIPPED'))
    def test_health_only_fake_echo_rejected(self):self.reject(lambda r,n,i:[row.update(argv=['echo','healthy']) for row in r['commands']])
    def test_dry_run_start_rejected(self):self.reject(lambda r,n,i:r['commands'][r['checks']['mysql.start']['command_ids'][0]-1]['argv'].append('--dry-run'))
    def test_wrong_commit_archive_run_and_contract_rejected(self):
        for key in ('repository','commit','run_id','run_attempt','archive_sha256','contract_sha256','handoff_sha256'):
            with self.subTest(key=key):self.reject(lambda r,n,i:r.update({key:'wrong'}))
    def test_native_other_archive_rejected(self):self.reject(lambda r,n,i:n['stages']['archive'].update(archive_sha256='f'*64))
    def test_failure_or_timeout_rejected(self):
        for change in ({'exit_code':1},{'timed_out':True},{'timeout_seconds':0},{'timeout_seconds':99999},{'stdout_sha256':None}):
            with self.subTest(change=change):self.reject(lambda r,n,i:r['commands'][0].update(change))
    def test_source_only_origin_rejected(self):self.reject(lambda r,n,i:r.update(course_origin='generated-source'))
    def test_environment_only_or_native_skipped_cannot_release(self):
        report,native,identity=evidence_fixture();native['stages']['native_validation']['native_tests']['cases'][0]['result']='ignored'
        with self.assertRaises(GateError):evaluate(native,report,identity)
    def test_wrong_image_ledger_rejected(self):self.reject(lambda r,n,i:r.update(image_ledger_sha256='f'*64))
    def test_unchecked_import_rejected(self):self.reject(lambda r,n,i:r['imports']['student'].update(post_runtime_revalidated=False))
    def test_learner_business_pass_rejected(self):self.reject(lambda r,n,i:r.update(learner_business_checks='PASS'))
    def test_default_user_project_rejected(self):self.reject(lambda r,n,i:r['ownership'].update(projects=['totalacademy-default']))
    def test_cleanup_missing_rejected(self):self.reject(lambda r,n,i:r['ownership'].update(empty_after=False))
    def test_missing_real_binding_rejected(self):self.reject(lambda r,n,i:r['checks']['rocketmq.bindings']['observations'].update(actual_loopback_only=False))
    def test_lost_volumes_rejected(self):self.reject(lambda r,n,i:r['checks']['mysql.preserved']['observations'].update(same_volume_ids=False))
    def test_recovery_changed_container_or_stage_rejected(self):
        for update in ({'stage':'02-reliability'},{'same_container_ids':False},{'same_mounts':False}):
            with self.subTest(update=update):self.reject(lambda r,n,i:r['checks']['capstone.same_stage']['observations'].update(update))
    def test_missing_browser_mobile_viewport_rejected(self):self.reject(lambda r,n,i:r['checks']['capstone.browser']['observations'].update(viewports=[1440]))

class HandoffFixture:
    def prepare(self,root):
        run=root/'run';(run/'evidence').mkdir(parents=True);(run/'dist').mkdir()
        student=run/'student';student.mkdir();contract=legacy_fixtures.ImportTests().fixture(student)
        import shutil,yaml
        shutil.copytree(student,run/'validation');educator=run/'validation'
        (educator/'section/lesson/task/src/F.java').write_bytes(b'answer')
        path=educator/'section/lesson/task/task-info.yaml';meta=yaml.safe_load(path.read_text());meta['files'][0]['placeholders'][0]['length']=6;path.write_text(yaml.safe_dump(meta))
        for name,data in [('shared/versions.env',b'FIXTURE=yes\n'),('scripts/gradle.sh',b'echo fixture\n')]:
            contract['files'][name]={'author_sha256':sha(data),'learner_sha256':sha(data),'placeholders':[]}
            for folder in (student,educator):
                (folder/name).parent.mkdir(parents=True,exist_ok=True);(folder/name).write_bytes(data);(folder/name).chmod(0o644)
        archive=b'explicit synthetic non-Academy ZIP fixture';(run/'dist/backend-interview-academy.zip').write_bytes(archive)
        native=native_fixture(sha(archive),len(archive))
        dump(run/'evidence/source-contract.json',contract)
        native['stages']['source_contract']={'status':'PASS','counts':contract['counts'],
            'sha256':sha((run/'evidence/source-contract.json').read_bytes()),
            'tasks':[{'path':row['path'],'expected_link_urls':row['expected_link_urls']} for row in contract['tasks']]}
        native['stages']['native_validation']={'status':'PASS',
            'native_tests':{'status':'PASS','expected':1,'observed':1,'missing':[],
                'cases':[{'task':'section/lesson/task','result':'success'}]},
            'description_links':{'status':'PASS','expected_tasks':1,'observed_tasks':1,'missing':{},'unexpected':{},'observed':1,
                'cases':[{'task':'section/lesson/task','link':'https://example.com/source','result':'success'}]}}
        dump(run/'evidence/summary.json',native)
        expected={key:native[key] for key in ('repository','commit','run_id','run_attempt')}
        return run,expected

class DockerOwnershipTests(unittest.TestCase):
    def case(self):
        acceptance=Acceptance.__new__(Acceptance);acceptance.course=Path('/run/handoff/educator');acceptance.projects=['totalacademy-ci-123-1','totalacademy-ci-123-1-capstone'];acceptance.current_services=('mysql',)
        acceptance.cfg={'MYSQL_PORT':'13306'};acceptance.report={'image_ledger':{'MYSQL_IMAGE':'mysql:fixture'},'ownership':{}};acceptance.containers={};acceptance.volumes={}
        labels={'com.docker.compose.project':acceptance.projects[0],'com.docker.compose.service':'mysql','com.docker.compose.project.working_dir':str(acceptance.course/'infra'),'com.docker.compose.project.config_files':str(acceptance.course/'infra/compose.yaml')}
        row={'id':'a'*64,'labels':labels,'state':{'running':True,'health':'healthy','oom':False},'ports':{'3306/tcp':[{'HostIp':'127.0.0.1','HostPort':'13306'}]},'image':'mysql:fixture','image_id':'sha256:fixture','mounts':[{'Type':'volume','Name':'ci-volume','Destination':'/var/lib/mysql'}]}
        acceptance.listed=lambda *args:[row['id']];acceptance.docker=lambda *args:json.dumps(row);acceptance.jsoninspect=lambda *args:{'com.docker.compose.project':acceptance.projects[0]}
        return acceptance,row
    def test_actual_binding_and_labels_pass(self):
        acceptance,row=self.case();self.assertTrue(acceptance.bindings()['actual_loopback_only'])
    def test_foreign_labels_paths_images_bindings_or_unhealthy_rejected(self):
        mutations=[lambda r:r['labels'].update({'com.docker.compose.project':'foreign'}),lambda r:r['labels'].update({'com.docker.compose.project.working_dir':'/foreign'}),lambda r:r['labels'].update({'com.docker.compose.project.config_files':'/foreign'}),lambda r:r.update(image='floating:latest'),lambda r:r['state'].update(health='starting'),lambda r:r['state'].update(oom=True),lambda r:r['ports']['3306/tcp'][0].update(HostIp='0.0.0.0'),lambda r:r['ports']['3306/tcp'].append({'HostIp':'::','HostPort':'13306'}),lambda r:r['ports']['3306/tcp'][0].update(HostPort='13307')]
        for mutation in mutations:
            acceptance,row=self.case();mutation(row)
            with self.subTest(mutation=mutation),self.assertRaises(GateError):acceptance.inspect()
    def test_stop_state_can_be_observed_without_faking_live_binding(self):
        acceptance,row=self.case();row['state']['running']=False;row['ports']={};self.assertFalse(acceptance.inspect(require_healthy=False)['mysql']['state']['running'])
    def test_unknown_or_writable_mount_rejected(self):
        for mount in ({'Type':'bind','Source':'/foreign','Destination':'/opt/app','RW':False},{'Type':'bind','Source':'/run/handoff/educator/a','Destination':'/opt/app','RW':True},{'Type':'tmpfs'}):
            acceptance,row=self.case();row['mounts']=[mount]
            with self.subTest(mount=mount),self.assertRaises((GateError,ValueError)):acceptance.inspect()
    def test_cleanup_never_runs_without_empty_before_proof(self):
        acceptance,row=self.case();acceptance.preflight_complete=False
        with self.assertRaises(GateError):acceptance.cleanup()


class SupplementalSafetyTests(unittest.TestCase):
    def test_environment_evidence_omits_raw_archive_config_and_symlink(self):
        from collect_environment_evidence import collect
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);run=root/'run';source=run/'evidence';source.mkdir(parents=True)
            (source/'summary.json').write_text('{"status":"FAIL","token":"SECRET"}')
            (source/'backend-interview-academy.zip').write_bytes(b'not evidence');(source/'.env').write_text('SECRET')
            (root/'foreign.log').write_text('FOREIGN_SECRET');(source/'command-1-stdout.log').symlink_to(root/'foreign.log')
            collect(run,root/'output');names={path.name for path in (root/'output').iterdir()}
            self.assertEqual(names,{'summary.json','collection.json'});self.assertNotIn('SECRET',(root/'output/summary.json').read_text())
            self.assertEqual(json.loads((root/'output/collection.json').read_text())['status'],'PARTIAL')
    def test_http_rejects_non_api_path_or_invalid_port_without_connect(self):
        from http_probe import call
        for port,path in [(8088,'//external/path'),(8088,'/api/../../private'),(0,'/api/health')]:
            with patch.dict(os.environ,{'CI':'true'}),patch('http_probe.urllib.request.build_opener') as opener:
                with self.assertRaises(ValueError):call(port,path,None,200)
                opener.assert_not_called()
    def test_http_redirects_forbidden(self):
        from http_probe import NoRedirect
        with self.assertRaises(ValueError):NoRedirect().redirect_request(None,None,None,None,None,None)
    def test_redis_requires_unique_ci_marker_before_socket(self):
        from redis_probe import probe
        with patch.dict(os.environ,{'CI':'true'}),patch('redis_probe.socket.create_connection') as connect:
            with self.assertRaises(ValueError):probe(16379,'user-default')
            connect.assert_not_called()
    def test_native_jobs_and_isolated_legal_preflight_have_no_own_ci_cycle(self):
        import yaml
        workflow=yaml.load((Path(__file__).resolve().parents[3]/'.github/workflows/academy-official.yml').read_text(),Loader=yaml.BaseLoader)
        self.assertEqual(set(workflow['jobs']),{'package','environment','legal-preflight'})
        self.assertEqual(workflow['jobs']['environment']['needs'],'package')
        self.assertNotIn('needs',workflow['jobs']['package'])
        for job in workflow['jobs'].values():self.assertEqual(job['runs-on'],'ubuntu-24.04')
        steps=workflow['jobs']['environment']['steps'];self.assertLessEqual(sum(int(s['timeout-minutes']) for s in steps),63)
        self.assertNotIn('check_source_ci.py',str(steps));self.assertIn('needs.package.outputs.handoff_sha256',str(steps))


class IndependentReviewRegressionTests(unittest.TestCase):
    def actual_release_fixture(self,path):
        report,native,identity=evidence_fixture();content=b'SYNTHETIC VERIFIED ARCHIVE BYTES'
        path.write_bytes(content);digest=sha(content)
        native['stages']['archive'].update(archive_sha256=digest,bytes=len(content));report['archive_sha256']=digest;identity['archive_sha256']=digest
        return report,native,identity,content
    def test_verified_native_bytes_still_cannot_release_without_full_course_verifiers(self):
        from release_gate import prepare_release
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'handoff').mkdir();archive=root/'handoff/course.zip'
            report,native,identity,content=self.actual_release_fixture(archive)
            result=evaluate(native,report,identity,archive)
            self.assertTrue(result['final_archive_rehashed'])
            self.assertEqual(result['status'],'BLOCKED');self.assertFalse(result['archive_upload_allowed'])
            self.assertEqual(len(result['blocked_gates']),3)
            with self.assertRaises(GateError):prepare_release(native,report,identity,archive,root/'release')
            self.assertFalse((root/'release').exists())
    def test_unverified_pass_flags_cannot_authorize_release(self):
        with tempfile.TemporaryDirectory() as directory:
            archive=Path(directory)/'course.zip'
            report,native,identity,content=self.actual_release_fixture(archive)
            native.update(native_ui_check_reset='PASS',negative_controls='PASS',extension_environment_lifecycle='PASS')
            native['stages']['native_validation']['negative_controls']='PASS'
            report['extension_environment_lifecycle']='PASS'
            result=evaluate(native,report,identity,archive)
            self.assertEqual(result['status'],'BLOCKED');self.assertFalse(result['archive_upload_allowed'])
    def test_tampered_truncated_empty_archive_cannot_release(self):
        from release_gate import prepare_release
        for mutate in (lambda value:value[:-1],lambda value:bytes([value[0]^1])+value[1:],lambda value:b''):
            with tempfile.TemporaryDirectory() as directory:
                root=Path(directory);(root/'handoff').mkdir();archive=root/'handoff/course.zip';report,native,identity,content=self.actual_release_fixture(archive)
                archive.write_bytes(mutate(content))
                with self.assertRaises(GateError):prepare_release(native,report,identity,archive,root/'release')
                self.assertFalse((root/'release').exists())
    def test_final_archive_symlink_or_parent_symlink_rejected(self):
        for parent in (False,True):
            with tempfile.TemporaryDirectory() as directory:
                root=Path(directory);real=root/'real';real.mkdir();archive=real/'course.zip';report,native,identity,content=self.actual_release_fixture(archive)
                if parent:(root/'link').symlink_to(real,target_is_directory=True);target=root/'link/course.zip'
                else:target=root/'link.zip';target.symlink_to(archive)
                with self.assertRaises(OSError):evaluate(native,report,identity,target)
    def test_archive_change_between_gate_and_copy_rejected(self):
        from release_gate import prepare_release
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'handoff').mkdir();archive=root/'handoff/course.zip';report,native,identity,content=self.actual_release_fixture(archive)
            with patch('release_gate.read_regular',side_effect=[content,b'mutated']):
                with self.assertRaises(GateError):prepare_release(native,report,identity,archive,root/'release')
            self.assertFalse((root/'release').exists())
    def test_native_archive_size_is_required_and_exact(self):
        for size in (None,True,0,999):
            with tempfile.TemporaryDirectory() as directory:
                archive=Path(directory)/'course.zip';report,native,identity,content=self.actual_release_fixture(archive);native['stages']['archive']['bytes']=size
                with self.assertRaises(GateError):evaluate(native,report,identity,archive)
    def test_final_workflow_upload_uses_only_gate_verified_release_copy(self):
        import yaml
        workflow=yaml.load((Path(__file__).resolve().parents[3]/'.github/workflows/academy-official.yml').read_text(),Loader=yaml.BaseLoader)
        steps=workflow['jobs']['environment']['steps'];gate=next(step for step in steps if step.get('id')=='release_gate')
        self.assertIn('--archive "$ENV_RUN/handoff/backend-interview-academy.zip"',gate['run']);self.assertIn('--release-dir "$ENV_RUN/release"',gate['run'])
        self.assertNotIn('hashlib',gate['run']);self.assertNotIn('/handoff/',steps[-1]['with']['path']);self.assertIn('/release/backend-interview-academy.zip',steps[-1]['with']['path'])
    def test_each_python_check_rejects_echo_and_wrong_argument_order(self):
        for name in ('redis.write_read','redis.read_after_restart','capstone.unavailable','capstone.replay'):
            for mutation in ('echo','nonpositional','port','missing_body_or_marker'):
                report,native,identity=evidence_fixture();index=report['checks'][name]['command_ids'][0]-1;argv=report['commands'][index]['argv']
                if mutation=='echo':argv[0]='echo'
                elif mutation=='nonpositional':argv.insert(1,'-c')
                elif mutation=='port':argv[argv.index('--port')+1]='65535'
                else:argv.pop()
                with self.subTest(check=name,mutation=mutation),self.assertRaises(GateError):validate_environment(report,native,identity)
    def test_each_java_probe_rejects_version_only_and_argument_only_illusion(self):
        for profile in ('mysql','kafka','rocketmq'):
            for step in ('write_read','read_after_restart'):
                name=profile+'.'+step
                for flag in ('-version','--help'):
                    report,native,identity=evidence_fixture();index=report['checks'][name]['command_ids'][0]-1;report['commands'][index]['argv'].insert(1,flag)
                    with self.subTest(check=name,flag=flag),self.assertRaises(GateError):validate_environment(report,native,identity)
    def test_compiler_gradle_browser_reject_noop_flags(self):
        for name in ('probe_compile','capstone.browser','launcher_prepare','launcher_verify'):
            report,native,identity=evidence_fixture()
            for identifier in report['checks'][name]['command_ids']:report['commands'][identifier-1]['argv'].append('--help')
            with self.subTest(check=name),self.assertRaises(GateError):validate_environment(report,native,identity)
    def test_external_gradle_artifacts_explicitly_filter_project_component(self):
        text=(Path(__file__).resolve().parents[1]/'probes/classpath.gradle').read_text()
        self.assertIn('incoming.artifactView',text);self.assertIn('componentFilter',text);self.assertIn('identifier instanceof ModuleComponentIdentifier',text)
        self.assertNotIn('runtimeClasspath.files',text);self.assertIn('external.files.files',text)

if __name__=='__main__':unittest.main()
