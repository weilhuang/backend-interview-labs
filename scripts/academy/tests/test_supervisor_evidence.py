"""Owned Python fixtures and static diagnostics only; no IDE/Java/Go/Docker."""
import hashlib
import itertools
import json
import os
import shutil
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import Mock, patch

BASE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(BASE))
import collect_evidence as evidence
import ui_session as session

def successful_result(**changes):
    return dict({'schema_version':1,'status':'PASS','exit_code':0,'cleanup_verified':True,
                 'cleanup_scope':'REGISTERED_SET_ONLY','termination':'CHILD_EXIT',
                 'operation':'CHILD_EXIT_OBSERVED','registered_process_count':1},**changes)

class SupervisorEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.run=self.root/'run';(self.run/'evidence').mkdir(parents=True)
        self.ui=self.root/'ui';self.ui.mkdir();self.output=self.root/'artifact'
    def tearDown(self):self.temp.cleanup()
    def write(self,path,value):
        if path.parent==self.ui and path.suffix=='.json' and type(value) is dict:value={'schema_version':1,**value}
        path.write_text(json.dumps(value) if isinstance(value,dict) else value)
    def collect(self,**kwargs):
        evidence.collect(self.run,self.output,ui_root=self.ui,**kwargs)
        return json.loads((self.output/'summary.json').read_text())
    def test_stale_running_is_failed_without_fabricating_exit_or_cleanup(self):
        self.write(self.run/'evidence/summary.json',{'status':'RUNNING','native_tests':'NOT_RUN'})
        summary=self.collect(job_status='failure',cleanup_exit=0)
        self.assertEqual(summary['status'],'FAIL');self.assertEqual(summary['observed_status'],'RUNNING')
        self.assertEqual(summary['initiating_cause'],'UNKNOWN')
        self.assertIsNone(summary['supervisor_evidence']['child_exit_code'])
        self.assertIsNone(summary['supervisor_evidence']['cleanup_verified'])
        self.assertEqual(summary['supervisor_evidence']['files']['supervisor-result.json'],'MISSING')
    def test_retains_terminal_child_exit_and_registered_cleanup(self):
        self.write(self.run/'evidence/summary.json',{'status':'RUNNING'})
        self.write(self.ui/'result.json',{'status':'FAILED','exit_code':7,'termination':'CHILD_EXIT',
                   'cleanup_verified':True,'cleanup_scope':'REGISTERED_SET_ONLY'})
        summary=self.collect();r=json.loads((self.output/'supervisor-result.json').read_text())
        self.assertEqual(r['exit_code'],7);self.assertEqual(r['termination'],'CHILD_EXIT')
        self.assertEqual(summary['supervisor_evidence']['child_exit_code'],7)
        self.assertTrue(summary['supervisor_evidence']['cleanup_verified'])
        self.assertEqual(summary['status'],'FAIL')
    def test_worker_success_does_not_turn_unfinalized_course_into_success(self):
        self.write(self.run/'evidence/summary.json',{'status':'RUNNING'})
        self.write(self.ui/'result.json',{'status':'PASS','exit_code':0,'cleanup_verified':True})
        self.assertEqual(self.collect()['status'],'FAIL')
    def test_missing_or_failed_supervisor_blocks_completed_success_summary(self):
        self.write(self.run/'evidence/summary.json',{'status':'PASS'})
        self.assertEqual(self.collect()['status'],'FAIL')
    def test_completed_course_and_verified_supervisor_remain_pass(self):
        self.write(self.run/'evidence/summary.json',{'status':'PASS','release_status':'BLOCKED'})
        self.write(self.ui/'result.json',successful_result())
        self.assertEqual(self.collect(cleanup_exit=0,job_status='success')['status'],'PASS')
    def test_cleanup_command_failure_does_not_claim_success(self):
        self.write(self.run/'evidence/summary.json',{'status':'PASS'})
        self.write(self.ui/'result.json',successful_result())
        summary=self.collect(cleanup_exit=1)
        self.assertEqual(summary['status'],'FAIL');self.assertEqual(summary['supervisor_evidence']['cleanup_command_exit_code'],1)
    def test_only_six_supervisor_filenames_no_profiles_or_environment(self):
        self.write(self.ui/'result.json',{'status':'FAILED','command':['PRIVATE_COMMAND'],'environment':{'X':'PRIVATE_ENV'},
            'error_details':{'operation':'SCAN_OWNED','exception_type':'OSError','errno':13,'code':'UNCLASSIFIED_EXCEPTION','message':'PRIVATE_MESSAGE'}})
        for name in ('private.json','state.json','profile.zip','environment.log'):(self.ui/name).write_text('PRIVATE_CONTENT')
        self.collect();text=''.join(p.read_text() for p in self.output.iterdir())
        for marker in ('PRIVATE_COMMAND','PRIVATE_ENV','PRIVATE_MESSAGE','PRIVATE_CONTENT'):self.assertNotIn(marker,text)
        self.assertEqual(set(p.name for p in self.output.iterdir()),{'summary.json','collection.json','supervisor-result.json'})
    def test_worker_streams_are_small_tails_and_redacted(self):
        for name in ('worker.stdout.log','worker.stderr.log','supervisor.log'):
            self.write(self.ui/name,'OLDER_MARKER\n'+'x'*50000+'\nAuthorization: Bearer SENTINEL_SECRET\npassword=SECRET_VALUE\nhttps://host/x?token=URL_SECRET\n/home/private/profile\nTAIL_MARKER\n')
        self.collect()
        for name in ('supervisor-worker.stdout.log','supervisor-worker.stderr.log','supervisor.log'):
            data=(self.output/name).read_bytes();self.assertLessEqual(len(data),evidence.SUPERVISOR_LOG_LIMIT)
            for value in (b'OLDER_MARKER',b'SENTINEL_SECRET',b'SECRET_VALUE',b'URL_SECRET',b'/home/private'):self.assertNotIn(value,data)
            self.assertIn(b'TAIL_MARKER',data)
    def test_oversized_json_omitted_without_losing_summary(self):
        self.write(self.run/'evidence/summary.json',{'status':'RUNNING'})
        self.write(self.ui/'result.json','x'*(evidence.SUPERVISOR_JSON_LIMIT+1))
        self.assertEqual(self.collect()['status'],'FAIL')
        self.assertFalse((self.output/'supervisor-result.json').exists())
        self.assertEqual(json.loads((self.output/'collection.json').read_text())['status'],'PARTIAL')
    def test_linked_stream_is_not_followed(self):
        secret=self.root/'secret';secret.write_text('DO_NOT_READ');(self.ui/'worker.stderr.log').symlink_to(secret)
        self.collect();self.assertFalse((self.output/'supervisor-worker.stderr.log').exists())
        self.assertEqual(json.loads((self.output/'collection.json').read_text())['status'],'PARTIAL')
    def test_linked_ui_parent_is_rejected(self):
        link=self.root/'ui-link';link.symlink_to(self.ui,target_is_directory=True)
        with self.assertRaises(OSError):evidence.collect(self.run,self.output,ui_root=link)
    def test_malformed_result_is_unknown_and_other_logs_survive(self):
        self.write(self.ui/'result.json','{"status":');self.write(self.ui/'supervisor.log','diagnostic')
        summary=self.collect();self.assertIsNone(summary['supervisor_evidence']['child_exit_code'])
        self.assertTrue((self.output/'supervisor.log').exists())
    def test_finalized_summary_uploaded_hash_matches_transformation(self):
        self.write(self.run/'evidence/summary.json',{'status':'RUNNING'})
        before=hashlib.sha256((self.run/'evidence/summary.json').read_bytes()).hexdigest();self.collect()
        record=json.loads((self.output/'collection.json').read_text())['hashes']['summary.json']
        self.assertEqual(record['original_sha256'],before)
        self.assertEqual(record['uploaded_sha256'],hashlib.sha256((self.output/'summary.json').read_bytes()).hexdigest())
        self.assertTrue(record['terminal_finalization'])


class SupervisorSchemaTests(unittest.TestCase):
    def test_success_matrix_has_exactly_one_verified_combination(self):
        values=itertools.product(['PASS','FAILED','RUNNING',None],
            [0,7,-15,None,False,True,'0',0.0],
            [True,False,None,1,'true'],['CHILD_EXIT','SUPERVISOR_EXCEPTION','UNKNOWN',None],
            ['success','failure','cancelled',None,'UNKNOWN'],[0,1,None,False,'0'])
        passes=0
        for status,exit_code,cleanup,termination,job,cleanup_exit in values:
            value=successful_result(status=status,exit_code=exit_code,cleanup_verified=cleanup,termination=termination)
            valid=evidence.verified_supervisor_success(value,job,cleanup_exit)
            expected=(status=='PASS' and type(exit_code) is int and exit_code==0 and cleanup is True
                      and termination=='CHILD_EXIT' and job=='success' and type(cleanup_exit) is int and cleanup_exit==0)
            self.assertEqual(valid,expected,(status,exit_code,cleanup,termination,job,cleanup_exit));passes+=valid
        self.assertEqual(passes,1)
    def test_all_published_fields_reject_nested_values(self):
        fields=['schema_version','status','exit_code','cleanup_verified','cleanup_scope','termination','operation',
                'error','cleanup_error','observation','registered_process_count']
        nested={'command':['SYNTHETIC_PRIVATE_COMMAND'],'environment':{'X':'SYNTHETIC_PRIVATE_ENV'}}
        for key in fields:
            for value in (nested,[nested]):
                with self.subTest(field=key),self.assertRaises(ValueError):
                    evidence.supervisor_document(successful_result(**{key:value}),'result.json')
        for detail in ('error_details','cleanup_error_details'):
            for key in ('operation','exception_type','errno','code'):
                value={'operation':'SCAN_OWNED','exception_type':'RuntimeError','code':'UNCLASSIFIED_EXCEPTION',key:nested}
                with self.subTest(detail=detail,field=key),self.assertRaises(ValueError):
                    evidence.supervisor_document(successful_result(**{detail:value}),'result.json')
    def test_boolean_and_numeric_confusion_rejected(self):
        cases={'schema_version':[True,1.0,'1',None,2], 'exit_code':[False,True,0.0,'0',256,-128],
               'registered_process_count':[True,1.0,'1',-1,513], 'cleanup_verified':[0,1,'true',[]]}
        for key,values in cases.items():
            for value in values:
                with self.subTest(field=key,value=value),self.assertRaises(ValueError):
                    evidence.supervisor_document(successful_result(**{key:value}),'result.json')
        for value in (True,False,1.0,'13',{},-1,4096):
            details={'operation':'SCAN_OWNED','exception_type':'OSError','code':'UNCLASSIFIED_EXCEPTION','errno':value}
            with self.subTest(errno=value),self.assertRaises(ValueError):
                evidence.supervisor_document(successful_result(error_details=details),'result.json')
    def test_missing_or_null_exit_and_cleanup_remain_unknown(self):
        value=successful_result();value.pop('exit_code');value.pop('cleanup_verified')
        result=evidence.supervisor_document(value,'result.json')
        self.assertIsNone(result['exit_code']);self.assertIsNone(result['cleanup_verified'])
        self.assertFalse(evidence.verified_supervisor_success(result,'success',0))
    def test_error_facts_cannot_coexist_with_verified_success(self):
        for key in ('error','error_details','cleanup_error','cleanup_error_details'):
            self.assertFalse(evidence.verified_supervisor_success(successful_result(**{key:None}),'success',0),key)
    def test_unknown_enums_are_rejected(self):
        for key in ('status','operation','termination','cleanup_scope','observation','error','cleanup_error'):
            with self.subTest(field=key),self.assertRaises(ValueError):
                evidence.supervisor_document(successful_result(**{key:'UNRECOGNIZED_VALUE'}),'result.json')
    def test_duplicate_keys_and_nonfinite_numbers_rejected(self):
        for raw in ('{"status":"FAILED","status":"PASS"}',
                    '{"error_details":{"code":"a","code":"b"}}','{"exit_code":NaN}','{"exit_code":Infinity}'):
            with self.subTest(raw=raw),self.assertRaises(ValueError):evidence.supervisor_json(raw)
    def test_nested_sensitive_payload_rejected_but_other_logs_survive(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'run/evidence').mkdir(parents=True);(root/'ui').mkdir()
            (root/'run/evidence/summary.json').write_text('{"status":"PASS"}')
            value=successful_result(error_details={'operation':{'command':['SYNTHETIC_PRIVATE_COMMAND'],
                'environment':{'X':'SYNTHETIC_PRIVATE_ENV'}},'exception_type':'RuntimeError','code':'UNCLASSIFIED_EXCEPTION'})
            (root/'ui/result.json').write_text(json.dumps(value));(root/'ui/supervisor.log').write_text('SAFE_DIAGNOSTIC')
            evidence.collect(root/'run',root/'out',ui_root=root/'ui',job_status='success',cleanup_exit=0)
            text=''.join(p.read_text() for p in (root/'out').iterdir())
            self.assertNotIn('SYNTHETIC_PRIVATE',text);self.assertIn('SAFE_DIAGNOSTIC',text)
            summary=json.loads((root/'out/summary.json').read_text());self.assertEqual(summary['status'],'FAIL')
            self.assertEqual(summary['supervisor_evidence']['files']['supervisor-result.json'],'UNAVAILABLE')
    def test_huge_nested_objects_and_duplicate_file_keep_other_diagnostics(self):
        for raw in ('{"schema_version":1,"status":"FAILED","status":"PASS"}',json.dumps({'operation':{'command':['PRIVATE']*4000}})):
            with self.subTest(kind=len(raw)),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);(root/'run/evidence').mkdir(parents=True);(root/'ui').mkdir()
                (root/'ui/result.json').write_text(raw);(root/'ui/supervisor.log').write_text('SAFE')
                evidence.collect(root/'run',root/'out',ui_root=root/'ui')
                self.assertFalse((root/'out/supervisor-result.json').exists());self.assertTrue((root/'out/supervisor.log').exists())
    def test_actual_collector_exit_and_job_combinations_fail_closed(self):
        for exit_code,job,cleanup_exit in itertools.product([0,7,None,False],['success','failure','cancelled',None],[0,None,False]):
            with tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);(root/'run/evidence').mkdir(parents=True);(root/'ui').mkdir()
                (root/'run/evidence/summary.json').write_text('{"status":"PASS"}')
                (root/'ui/result.json').write_text(json.dumps(successful_result(exit_code=exit_code)))
                evidence.collect(root/'run',root/'out',ui_root=root/'ui',job_status=job,cleanup_exit=cleanup_exit)
                summary=json.loads((root/'out/summary.json').read_text())
                expected=type(exit_code) is int and exit_code==0 and job=='success' and type(cleanup_exit) is int and cleanup_exit==0
                self.assertEqual(summary['status']=='PASS',expected,(exit_code,job,cleanup_exit))
    def test_invalid_job_and_cleanup_objects_are_not_serialized(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'run/evidence').mkdir(parents=True);(root/'ui').mkdir()
            (root/'run/evidence/summary.json').write_text('{"status":"PASS"}')
            (root/'ui/result.json').write_text(json.dumps(successful_result()))
            evidence.collect(root/'run',root/'out',ui_root=root/'ui',job_status={'environment':'PRIVATE'},cleanup_exit={'command':'PRIVATE'})
            text=(root/'out/summary.json').read_text();self.assertNotIn('PRIVATE',text)
            summary=json.loads(text);self.assertEqual(summary['status'],'FAIL')
            self.assertEqual(summary['supervisor_evidence']['job_status_at_collection'],'UNKNOWN')
            self.assertIsNone(summary['supervisor_evidence']['cleanup_command_exit_code'])


class SupervisorProcessTests(unittest.TestCase):
    def test_owned_python_root_waits_for_its_child(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);session.put(root/'state.json',session.budget_record(session.process_info(os.getpid()),3600))
            code="import subprocess,sys; p=subprocess.Popen([sys.executable,'-c','import time;time.sleep(.6)'],start_new_session=True);p.wait();raise SystemExit(p.returncode)"
            with patch.object(session.signal,'signal'):
                self.assertEqual(session.worker(root,[sys.executable,'-c',code]),0)
            result=json.loads((root/'result.json').read_text());self.assertEqual(result['exit_code'],0)
            self.assertEqual(result['termination'],'CHILD_EXIT');self.assertTrue(result['cleanup_verified'])
            # Some sandbox kernels expose an empty task/children view. The
            # child exits naturally; only the reported registered set is proved.
            self.assertGreaterEqual(result['registered_process_count'],1)
    def test_valid_mock_child_is_registered_after_all_identity_checks(self):
        parent={'pid':100,'ppid':50,'uid':1000,'pgrp':100,'session':100,'start_time':'10'}
        child={'pid':200,'ppid':100,'uid':1000,'pgrp':200,'session':200,'start_time':'20'}
        owned=session.Owned(time.monotonic()+10);owned.members={100:(parent,700)};owned.root_registered=True
        with patch.object(session,'matching',return_value=True),patch.object(session,'direct_candidates',side_effect=lambda p,d:{200} if p['pid']==100 else set()),patch.object(session,'process_info',return_value=child),patch.object(session.os,'pidfd_open',return_value=900),patch.object(session,'live',return_value=True):
            owned.scan()
        self.assertEqual(owned.members[200],(child,900))
    def test_fixed_owned_failure_reasons_have_distinct_codes(self):
        cases={'OWNERSHIP_UNVERIFIED':'OWNERSHIP_UNVERIFIED','进程元数据过大':'PROCESS_METADATA_LIMIT',
               '进程登记预算耗尽':'REGISTRATION_DEADLINE','子进程登记预算耗尽':'REGISTRATION_DEADLINE',
               '自有子链枚举预算耗尽':'CHILD_ENUMERATION_BUDGET','自有子链元数据过大':'CHILD_METADATA_LIMIT',
               '自有子链数量上限':'CHILD_COUNT_LIMIT','已登记进程上限':'REGISTERED_COUNT_LIMIT',
               '已登记进程未全部退出':'REGISTERED_CLEANUP_INCOMPLETE'}
        for message,code in cases.items():
            with self.subTest(code=code):
                result=session.exception_diagnostic(RuntimeError(message),'SCAN_OWNED')
                self.assertEqual(result['code'],code);self.assertNotIn('message',result)
    def test_owned_python_early_exit_is_recorded_without_checkpoint(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'ui'
            with self.assertRaises(RuntimeError):session.launch(root,[sys.executable,'-c','raise SystemExit(7)'])
            result=json.loads((root/'result.json').read_text());launch=json.loads((root/'launch-result.json').read_text())
            self.assertEqual(result['exit_code'],7);self.assertEqual(result['termination'],'CHILD_EXIT')
            self.assertTrue(result['cleanup_verified']);self.assertEqual(launch['status'],'FAILED')
            self.assertEqual(launch['error_details']['operation'],'AWAIT_STAGE_1')
    def test_scan_exception_has_operation_and_type_without_message(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);session.put(root/'state.json',session.budget_record(session.process_info(os.getpid()),3600))
            owned=Mock();owned.scan.side_effect=OSError(13,'PRIVATE_CMD token=SECRET')
            proc=Mock();proc.poll.return_value=None;proc.wait.return_value=-15
            with patch.object(session,'Owned',return_value=owned),patch.object(session.subprocess,'Popen',return_value=proc),patch.object(session.signal,'signal'):
                self.assertEqual(session.worker(root,['PRIVATE_COMMAND']),1)
            r=json.loads((root/'result.json').read_text());self.assertEqual(r['termination'],'SUPERVISOR_EXCEPTION')
            self.assertEqual(r['error_details'],{'operation':'SCAN_OWNED','exception_type':'PermissionError','errno':13,'code':'UNCLASSIFIED_EXCEPTION'})
            self.assertNotIn('SECRET',json.dumps(r));self.assertNotIn('PRIVATE',json.dumps(r));owned.stop.assert_called_once()
    def test_initialization_exception_still_has_terminal_result(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'state.json').write_text('{}')
            with patch.object(session,'read_outer_deadline',side_effect=ValueError('PRIVATE')),patch.object(session.signal,'signal'):
                self.assertEqual(session.worker(root,['never-run']),1)
            r=json.loads((root/'result.json').read_text());self.assertEqual(r['error_details']['operation'],'INITIALIZE')
            self.assertIsNone(r['exit_code']);self.assertIsNone(r['cleanup_verified'])
    def test_cleanup_unknown_is_not_child_cleanup_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);session.cleanup(root)
            r=json.loads((root/'cleanup-result.json').read_text());self.assertEqual(r['observation'],'NO_SUPERVISOR_IDENTITY')
            self.assertIsNone(r['cleanup_verified'])
    def test_cleanup_exception_is_recorded_and_reraised(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            with patch.object(session,'_cleanup',side_effect=RuntimeError('PRIVATE')):
                with self.assertRaises(RuntimeError):session.cleanup(root)
            r=json.loads((root/'cleanup-result.json').read_text());self.assertEqual(r['status'],'FAILED')
            self.assertEqual(r['error_details']['operation'],'CLEANUP_SUPERVISOR');self.assertNotIn('PRIVATE',json.dumps(r))


class WorkflowEvidenceTests(unittest.TestCase):
    def evidence_step(self):
        import yaml
        workflow=yaml.load((BASE.parents[1]/'.github/workflows/academy-official.yml').read_text(),Loader=yaml.BaseLoader)
        return next(s for s in workflow['jobs']['package']['steps'] if s.get('id')=='evidence')
    def shell_fixture(self,root):
        scripts=root/'scripts/academy';scripts.mkdir(parents=True)
        for name in ('collect_evidence.py','safe_io.py','thread_diagnostics.py','display_diagnostic.py','project_trust.py','trust_window.py','ui_control.py','post_trust_diagnostic.py','post_trust_stacks.py','plugin_agreement.py','modal_window.py','modal_pixels.py','modal_fixture.py','academy-legal.json','profile_control.py','profile_window.py','apparmor_profile.py','restart_family.py','restart_session.py'):shutil.copyfile(BASE/name,scripts/name)
        (scripts/'ui_session.py').write_text('raise SystemExit(3)\n')
        temporary=root/'temporary';temporary.mkdir();ui=temporary/'ui';ui.mkdir()
        run=temporary/'academy-run-123-1';(run/'evidence').mkdir(parents=True)
        (run/'evidence/summary.json').write_text('{"status":"RUNNING"}')
        env=dict(os.environ,RUNNER_TEMP=str(temporary),UI_RUN=str(ui),GITHUB_RUN_ID='123',GITHUB_RUN_ATTEMPT='1',
                 GITHUB_ENV=str(root/'env-output'),GITHUB_OUTPUT=str(root/'step-output'))
        script=self.evidence_step()['run'].replace('${{ job.status }}','failure')
        return script,env,temporary/'academy-artifact-evidence-123-1'
    def test_real_shell_cleanup_failure_preserves_new_collected_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);script,env,artifact=self.shell_fixture(root)
            result=subprocess.run(['bash','-e','-c',script],cwd=root,env=env,capture_output=True,timeout=10)
            self.assertEqual(result.returncode,3)
            self.assertIn('collected=true',(root/'step-output').read_text())
            summary=json.loads((artifact/'summary.json').read_text())
            self.assertEqual(summary['status'],'FAIL');self.assertEqual(summary['supervisor_evidence']['cleanup_command_exit_code'],3)
    def test_real_shell_collector_failure_cannot_reuse_old_artifact(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);script,env,artifact=self.shell_fixture(root);artifact.mkdir()
            (artifact/'summary.json').write_text('OLD_EVIDENCE')
            result=subprocess.run(['bash','-e','-c',script],cwd=root,env=env,capture_output=True,timeout=10)
            self.assertNotEqual(result.returncode,0);self.assertFalse((root/'step-output').exists())
            self.assertEqual((artifact/'summary.json').read_text(),'OLD_EVIDENCE')
    def test_collection_upload_survives_cleanup_failure_and_includes_ui_root(self):
        import yaml
        workflow=yaml.load((BASE.parents[1]/'.github/workflows/academy-official.yml').read_text(),Loader=yaml.BaseLoader)
        steps=workflow['jobs']['package']['steps'];step=next(s for s in steps if s.get('id')=='evidence')
        self.assertEqual(step['if'],'always()');self.assertIn('--ui-root "$UI_RUN"',step['run'])
        self.assertIn('--cleanup-exit "$cleanup_status"',step['run'])
        self.assertLess(step['run'].index('collected=true'),step['run'].rindex('exit "$cleanup_status"'))
        upload=next(s for s in steps if s.get('name')=='保存小型验收证据')
        self.assertEqual(upload['if'],"always() && steps.evidence.outputs.collected == 'true'")


if __name__=='__main__':unittest.main()
