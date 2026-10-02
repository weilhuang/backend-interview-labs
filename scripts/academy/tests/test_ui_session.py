"""普通机械字段/预算/发布链回归；不把 fixture 当作真实 UI 验收。"""
from pathlib import Path
import importlib.util, io, json, os, sys, tempfile, unittest, time
from contextlib import redirect_stdout
from unittest.mock import patch, Mock, MagicMock
BASE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(BASE))
import ui_control as control
import ui_session as session

class ControlTest(unittest.TestCase):
    def setUp(self):
        self.request={'schema':1,'run_id':'123','run_attempt':'1','stage':1,
            'screenshot_sha256':'a'*64,'eua_sha256':control.EUA_SHA256,'action':'CHECK_EUA'}
    def check_bad(self,**changed):
        with self.assertRaises(ValueError):control.validate_control({**self.request,**changed},self.request)
    def test_exact_current_request(self):self.assertEqual(control.validate_control(self.request,self.request),self.request)
    def test_other_run(self):self.check_bad(run_id='124')
    def test_other_attempt(self):self.check_bad(run_attempt='2')
    def test_previous_stage(self):self.check_bad(stage=2,action='CONTINUE_EUA')
    def test_wrong_screenshot(self):self.check_bad(screenshot_sha256='b'*64)
    def test_other_agreement(self):self.check_bad(eua_sha256='b'*64)
    def test_wrong_action(self):self.check_bad(action='CONTINUE_EUA')
    def test_arbitrary_action(self):self.check_bad(action='RUN_SHELL')
    def test_no_coordinates(self):self.check_bad(x=1,y=2)
    def test_no_text(self):self.check_bad(text='anything')
    def test_no_unknown_field(self):self.check_bad(extra=True)
    def test_boolean_schema_rejected(self):self.check_bad(schema=True)
    def test_boolean_stage_rejected(self):self.check_bad(stage=True)
    def test_non_string_run(self):self.check_bad(run_id=123)
    def test_invalid_run(self):self.check_bad(run_id='../123')
    def test_incomplete_digest(self):self.check_bad(screenshot_sha256='a')
    def test_telemetry_only_reject(self):
        value={**self.request,'stage':3,'action':'DECLINE_USAGE'}
        self.assertEqual(control.validate_control(value,value)['action'],'DECLINE_USAGE')
        with self.assertRaises(ValueError):control.validate_control({**value,'action':'SEND_USAGE'},value)
    def test_duplicate_json_key(self):
        with self.assertRaises(ValueError):control.strict_json(b'{"stage":1,"stage":1}')
    def test_small_regular_json(self):self.assertEqual(control.strict_json(b'{"ok":true}'),{'ok':True})
    def test_no_redirect(self):
        with self.assertRaises(ValueError):control.NoRedirect().redirect_request(None,None,302,'',{},'https://elsewhere.invalid')
    def test_absent_control_never_writes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);stage=root/'stage-1';stage.mkdir()
            session.put(stage/'request.json',self.request)
            session.put(root/'ui-deadline.json',{'monotonic_deadline':0})
            with patch.object(control,'read_ui_deadline',return_value=0):
                with self.assertRaises(TimeoutError):control.receive(root,1)
            self.assertFalse((stage/'control.json').exists())
    def test_consumed_action_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);stage=root/'stage-1';stage.mkdir()
            session.put(stage/'request.json',self.request);session.put(stage/'control.json',self.request)
            session.put(root/'ui-deadline.json',session.budget_record(session.process_info(os.getpid()),control.UI_BUDGET_SECONDS))
            with self.assertRaises(ValueError):control.receive(root,1)
    def test_request_is_not_preapproval(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);session.put(root/'request.json',self.request)
            self.assertFalse((root/'control.json').exists())

class SessionTest(unittest.TestCase):
    def test_environment_excludes_credentials(self):
        with patch.dict(os.environ,{'GH_TOKEN':'test-only','ACTIONS_RUNTIME_TOKEN':'test-only','IDEA_PROPERTIES':'private','GITHUB_RUN_ID':'123'},clear=True):
            self.assertEqual(session.clean_env(),{'GITHUB_RUN_ID':'123'})
    def test_same_pid_different_start_time_is_not_owned(self):
        with patch.object(session,'start_time',return_value='new'):
            self.assertFalse(session.identity_alive({'pid':123,'start_time':'old'}))
    def test_exited_identity_is_not_alive(self):
        with patch.object(session,'start_time',side_effect=ProcessLookupError):
            self.assertFalse(session.identity_alive({'pid':123,'start_time':'old'}))
    def test_current_identity_alive(self):
        with patch.object(session,'start_time',return_value='same'):
            self.assertTrue(session.identity_alive({'pid':123,'start_time':'same'}))
    def test_evidence_is_exclusive(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'record.json';session.put(p,{'ok':1})
            with self.assertRaises(FileExistsError):session.put(p,{'ok':2})
    def test_failed_official_exit_never_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            r=Path(tmp);session.put(r/'state.json',session.budget_record(session.process_info(os.getpid()),3600))
            session.put(r/'result.json',{'status':'FAILED','cleanup_verified':True})
            with self.assertRaises(RuntimeError):session.finish(r)
    def test_unverified_cleanup_never_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            r=Path(tmp);session.put(r/'state.json',session.budget_record(session.process_info(os.getpid()),3600))
            session.put(r/'result.json',{'status':'PASS','cleanup_verified':False})
            with self.assertRaises(RuntimeError):session.finish(r)
    def test_all_original_success_and_cleanup_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            r=Path(tmp);session.put(r/'state.json',session.budget_record(session.process_info(os.getpid()),3600))
            session.put(r/'result.json',{'status':'PASS','cleanup_verified':True});session.finish(r)
    def test_expired_outer_budget_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            r=Path(tmp);session.put(r/'state.json',{'deadline':0})
            with patch.object(session,'read_outer_deadline',return_value=0):
                with self.assertRaises(TimeoutError):session.finish(r)
    def test_receiving_exact_record(self):
        request=ControlTest();request.setUp()
        with tempfile.TemporaryDirectory() as tmp:
            r=Path(tmp);s=r/'stage-1';s.mkdir();session.put(s/'request.json',request.request)
            session.put(r/'ui-deadline.json',session.budget_record(session.process_info(os.getpid()),control.UI_BUDGET_SECONDS))
            with patch.object(control,'fetch_control',return_value=request.request),patch.dict(os.environ,{'GH_TOKEN':'fixture','GITHUB_REPOSITORY':'owner/repo'}):control.receive(r,1)
            self.assertEqual(json.loads((s/'control.json').read_bytes()),request.request)

class ProcessLifecycleTest(unittest.TestCase):
    def test_same_background_session_across_checkpoint(self):
        with tempfile.TemporaryDirectory() as tmp:
            r=Path(tmp)/'session'
            code="from pathlib import Path;import time; r=Path("+repr(str(r))+ ");s=r/'stage-1';s.mkdir();(s/'request.json').write_text('{}');time.sleep(.5)"
            session.launch(r,[sys.executable,'-c',code])
            self.assertTrue((r/'stage-1/request.json').is_file())
            session.finish(r)
            result=json.loads((r/'result.json').read_bytes())
            self.assertEqual(result['exit_code'],0);self.assertTrue(result['cleanup_verified'])
            session.cleanup(r)
    def test_early_exit_without_ui_checkpoint_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            r=Path(tmp)/'session'
            with self.assertRaises(RuntimeError):session.launch(r,[sys.executable,'-c','raise SystemExit(3)'])
            result=json.loads((r/'result.json').read_bytes())
            self.assertEqual(result['exit_code'],3);self.assertEqual(result['status'],'FAILED')
    def test_cancel_stops_only_owned_fixture_session(self):
        with tempfile.TemporaryDirectory() as tmp:
            r=Path(tmp)/'session'
            code="from pathlib import Path;import time; r=Path("+repr(str(r))+ ");s=r/'stage-1';s.mkdir();(s/'request.json').write_text('{}');time.sleep(20)"
            session.launch(r,[sys.executable,'-c',code]);session.cleanup(r)
            result=json.loads((r/'result.json').read_bytes())
            self.assertEqual(result['status'],'FAILED');self.assertTrue(result['cleanup_verified'])

class OwnershipRevisionTest(unittest.TestCase):
    def setUp(self):
        self.parent={'pid':100,'ppid':50,'uid':1000,'pgrp':100,'session':100,'start_time':'10'}
        self.child={'pid':200,'ppid':100,'uid':1000,'pgrp':100,'session':100,'start_time':'20'}
    def registry(self):
        obj=session.Owned(999999999999);obj.members={100:(self.parent,700)};obj.root_registered=True
        return obj
    def test_stale_child_number_now_unrelated_never_adopted(self):
        owned=self.registry();unrelated={**self.child,'ppid':999,'start_time':'30'}
        with patch.object(session,'matching',return_value=True),patch.object(session,'direct_candidates',return_value={200}),patch.object(session,'process_info',return_value=unrelated),patch.object(session.os,'pidfd_open') as op:
            owned.scan();op.assert_not_called()
        self.assertEqual(set(owned.members),{100})
    def test_child_reused_between_read_and_pidfd_open_rejected(self):
        owned=self.registry()
        with patch.object(session,'matching',return_value=True),patch.object(session,'direct_candidates',return_value={200}),patch.object(session,'process_info',side_effect=[self.child,{**self.child,'ppid':999,'start_time':'30'}]),patch.object(session.os,'pidfd_open',return_value=900),patch.object(session,'live',return_value=True),patch.object(session.os,'close') as close:
            owned.scan();close.assert_called_once_with(900)
        self.assertNotIn(200,owned.members)
    def test_parent_replaced_after_child_open_rejected(self):
        owned=self.registry()
        with patch.object(session,'matching',side_effect=[True,False]),patch.object(session,'direct_candidates',return_value={200}),patch.object(session,'process_info',return_value=self.child),patch.object(session.os,'pidfd_open',return_value=900),patch.object(session,'live',return_value=True),patch.object(session.os,'close') as close:
            owned.scan();close.assert_called_once_with(900)
        self.assertNotIn(200,owned.members)
    def test_child_uid_change_refused_before_open(self):
        owned=self.registry()
        with patch.object(session,'matching',return_value=True),patch.object(session,'direct_candidates',return_value={200}),patch.object(session,'process_info',return_value={**self.child,'uid':2000}),patch.object(session.os,'pidfd_open') as op:
            owned.scan();op.assert_not_called()
    def test_child_unrelated_session_refused_before_open(self):
        owned=self.registry()
        with patch.object(session,'matching',return_value=True),patch.object(session,'direct_candidates',return_value={200}),patch.object(session,'process_info',return_value={**self.child,'session':999}),patch.object(session.os,'pidfd_open') as op:
            owned.scan();op.assert_not_called()
    def test_child_dead_pidfd_refused(self):
        owned=self.registry()
        with patch.object(session,'matching',return_value=True),patch.object(session,'direct_candidates',return_value={200}),patch.object(session,'process_info',return_value=self.child),patch.object(session.os,'pidfd_open',return_value=900),patch.object(session,'live',return_value=False),patch.object(session.os,'close') as close:
            owned.scan();close.assert_called_once_with(900)
        self.assertNotIn(200,owned.members)
    def test_registered_pid_reuse_does_not_reopen(self):
        owned=self.registry();owned.members[200]=(self.child,900)
        with patch.object(session,'matching',side_effect=lambda meta,fd:fd==700),patch.object(session,'direct_candidates',return_value={200}),patch.object(session.os,'pidfd_open') as op:
            owned.scan();op.assert_not_called()
    def test_no_new_adoption_during_cleanup(self):
        owned=self.registry()
        with patch.object(owned,'scan',side_effect=AssertionError('must not scan')),patch.object(session,'live',return_value=False),patch.object(session.signal,'pidfd_send_signal') as send,patch.object(session.os,'close'):
            owned.stop();send.assert_not_called()
    def test_expired_registration_budget_refuses_scan(self):
        owned=self.registry();owned.deadline=0
        with patch.object(session,'direct_candidates') as discover:
            with self.assertRaises(TimeoutError):owned.scan()
            discover.assert_not_called()
    def test_no_full_proc_enumeration_in_implementation(self):
        source=(BASE/'ui_session.py').read_text()
        self.assertNotIn("Path('/proc').iterdir",source)
        self.assertIn("/task",source)
    def test_worker_registration_failure_still_cleans_and_reports(self):
        with tempfile.TemporaryDirectory() as tmp:
            r=Path(tmp);session.put(r/'state.json',session.budget_record(session.process_info(os.getpid()),3600))
            proc=Mock();proc.wait.return_value=1
            owned=Mock();owned.register_root.side_effect=RuntimeError('OWNERSHIP_UNVERIFIED');owned.stop.side_effect=RuntimeError('OWNERSHIP_UNVERIFIED')
            with patch.object(session,'Owned',return_value=owned),patch.object(session.subprocess,'Popen',return_value=proc),patch.object(session.signal,'signal'):
                self.assertEqual(session.worker(r,['fixture']),1)
            owned.stop.assert_called_once();proc.wait.assert_called_once()
            result=json.loads((r/'result.json').read_bytes());self.assertFalse(result['cleanup_verified']);self.assertEqual(result['status'],'FAILED')
    def test_launch_state_failure_after_spawn_cleans(self):
        with tempfile.TemporaryDirectory() as tmp:
            r=Path(tmp)/'session';original=session.put
            proc=Mock();owned=Mock();owned.register_root.return_value=self.parent
            def write(path,value):
                if path.name=='supervisor.json':raise OSError('fixture')
                return original(path,value)
            with patch.object(session,'put',side_effect=write),patch.object(session,'Owned',return_value=owned),patch.object(session.subprocess,'Popen',return_value=proc):
                with self.assertRaises(OSError):session.launch(r,['fixture'])
            owned.stop.assert_called_once();proc.wait.assert_called_once()
    def test_server_state_failure_after_spawn_cleans(self):
        with tempfile.TemporaryDirectory() as tmp:
            r=Path(tmp);session.put(r/'state.json',session.budget_record(session.process_info(os.getpid()),3600))
            proc=Mock();owned=Mock();owned.register_root.return_value=self.parent
            with patch.object(session,'put',side_effect=OSError('fixture')),patch.object(session,'Owned',return_value=owned),patch.object(session.subprocess,'Popen',return_value=proc),patch.object(session.signal,'signal'):
                with self.assertRaises(OSError):session.server_session(r,['fixture'])
            owned.stop.assert_called_once();proc.wait.assert_called_once()
    def test_ui_deadline_write_failure_after_spawn_cleans(self):
        import hashlib
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);proc=Mock();owned=Mock();owned.register_root.return_value=self.child
            identity=Mock();jar=MagicMock();jar.__enter__.return_value=jar;jar.getinfo.return_value.file_size=7;jar.read.return_value=b'fixture'
            with patch.object(session.zipfile,'ZipFile',return_value=jar),patch.object(session,'EUA_SHA256',hashlib.sha256(b'fixture').hexdigest()),patch.object(session,'Owned',return_value=owned),patch.object(session,'DisplayIdentity',return_value=identity),patch.object(session.subprocess,'Popen',return_value=proc),patch.object(session,'put',side_effect=OSError('fixture')),patch.object(session.signal,'signal'):
                with self.assertRaises(OSError):session.display_session(root,root,['fixture'])
            owned.stop.assert_called_once();identity.close.assert_called_once();proc.wait.assert_called_once()

class DisplayIdentityRevisionTest(unittest.TestCase):
    def identity(self):
        obj=session.DisplayIdentity();obj.authority=Path('/owned/auth');obj.socket=Path('/owned/socket')
        obj.metadata={'display':':99','authority':{'ino':1},'socket':{'ino':2}}
        obj.handles={'wrapper':({'pid':100},700),'server':({'pid':200},800),'ide':({'pid':300},900)}
        return obj
    def test_display_number_replaced(self):
        obj=self.identity()
        with patch.dict(os.environ,{'DISPLAY':':100'}):
            with self.assertRaises(RuntimeError):obj.verify()
    def test_server_or_ide_pidfd_dead_refuses(self):
        for failed in [700,800,900]:
            obj=self.identity()
            with patch.dict(os.environ,{'DISPLAY':':99'}),patch.object(session,'matching',side_effect=lambda meta,fd:fd!=failed):
                with self.assertRaises(RuntimeError):obj.verify()
    def test_auth_file_replaced_refuses(self):
        obj=self.identity()
        with patch.dict(os.environ,{'DISPLAY':':99'}),patch.object(session,'matching',return_value=True),patch.object(session,'file_identity',return_value={'ino':99}):
            with self.assertRaises(RuntimeError):obj.verify()
    def test_socket_replaced_refuses(self):
        obj=self.identity()
        with patch.dict(os.environ,{'DISPLAY':':99'}),patch.object(session,'matching',return_value=True),patch.object(session,'file_identity',side_effect=[{'ino':1},{'ino':99}]):
            with self.assertRaises(RuntimeError):obj.verify()
    def test_current_registered_display_matches(self):
        obj=self.identity()
        with patch.dict(os.environ,{'DISPLAY':':99'}),patch.object(session,'matching',return_value=True),patch.object(session,'file_identity',side_effect=[{'ino':1},{'ino':2}]):obj.verify()
    def test_java_rechecks_inherited_pidfd_before_input(self):
        helper=(BASE/'probes/AgreementUi.java').read_text()
        self.assertIn('/proc/self/fdinfo',helper)
        self.assertLess(helper.rindex('verifyOwned(binding);',0,helper.index('robot.mousePress')),helper.index('robot.mousePress'))
    def test_java_rejects_unreaped_zombie_and_dead_state(self):
        helper=(BASE/'probes/AgreementUi.java').read_text()
        guard='fields[0].equals("Z") || fields[0].equals("X")'
        self.assertIn(guard,helper)
        self.assertLess(helper.index(guard),helper.index('robot.mousePress'))
    def test_owned_exit_can_keep_fdinfo_pid_until_reaped(self):
        import subprocess, select
        proc=subprocess.Popen([sys.executable,'-c','pass'])
        fd=os.pidfd_open(proc.pid)
        try:
            self.assertTrue(select.select([fd],[],[],5)[0])
            info=Path(f'/proc/self/fdinfo/{fd}').read_text()
            self.assertEqual(next(line.split(':',1)[1].strip() for line in info.splitlines() if line.startswith('Pid:')),str(proc.pid))
            state=Path(f'/proc/{proc.pid}/stat').read_text().rsplit(')',1)[1].split()[0]
            self.assertIn(state,('Z','X'))
        finally:
            proc.wait(timeout=5);os.close(fd)
    def test_atomic_record_never_replaces_existing(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'record.json';session.put(p,{'first':1})
            with self.assertRaises(FileExistsError):session.put(p,{'second':2})
            self.assertEqual(json.loads(p.read_bytes()),{'first':1});self.assertEqual(list(Path(tmp).glob('.pending-*')),[])

class AbsoluteBudgetRevisionTest(unittest.TestCase):
    def setUp(self):self.owner={'pid':100,'uid':1000,'pgrp':100,'session':100,'start_time':'12345'}
    def test_exact_kernel_start_deadline(self):
        value=session.budget_record(self.owner,3600)
        self.assertEqual(control.checked_budget(value,3600,self.owner),int(self.owner['start_time'])/os.sysconf('SC_CLK_TCK')+3600)
    def test_fake_fresh_deadline_rejected(self):
        value=session.budget_record(self.owner,3600);value['monotonic_deadline']+=60
        with self.assertRaises(ValueError):control.checked_budget(value,3600,self.owner)
    def test_fresh_owner_birth_rejected(self):
        value=session.budget_record({**self.owner,'start_time':'22345'},3600)
        with self.assertRaises(ValueError):control.checked_budget(value,3600,self.owner)
    def test_child_stage_cannot_expand_budget(self):
        value=session.budget_record(self.owner,3600)
        with self.assertRaises(ValueError):control.checked_budget(value,control.UI_BUDGET_SECONDS,self.owner)
    def test_ui_stage_cannot_reset_deadline(self):
        value=session.budget_record(self.owner,control.UI_BUDGET_SECONDS);value['monotonic_deadline']+=1
        with self.assertRaises(ValueError):control.checked_budget(value,control.UI_BUDGET_SECONDS,self.owner)
    def test_boolean_or_unknown_budget_rejected(self):
        value=session.budget_record(self.owner,control.UI_BUDGET_SECONDS);value['budget_seconds']=True
        with self.assertRaises(ValueError):control.checked_budget(value,control.UI_BUDGET_SECONDS,self.owner)
    def test_repeated_phase_read_is_same_absolute_deadline(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);owner=session.process_info(os.getpid());session.put(root/'state.json',session.budget_record(owner,3600))
            before=session.read_outer_deadline(root)
            with patch.object(session.time,'monotonic',return_value=999999999999):after=session.read_outer_deadline(root)
            self.assertEqual(before,after)


class SharedUiDeadlineTest(unittest.TestCase):
    def setUp(self):
        self.owner={'pid':100,'uid':1000,'pgrp':100,'session':100,
                    'start_time':str(100*os.sysconf('SC_CLK_TCK'))}
        self.record=session.budget_record(self.owner,control.UI_BUDGET_SECONDS)
    def prepare(self,root,stage):
        folder=root/f'stage-{stage}';folder.mkdir()
        request={'schema':1,'run_id':'123','run_attempt':'1','stage':stage,
                 'screenshot_sha256':'a'*64,'eua_sha256':control.EUA_SHA256,'action':control.ACTIONS[stage]}
        session.put(folder/'request.json',request)
        return request
    def receive(self,root,stage,now,value):
        output=io.StringIO()
        with patch.object(session,'process_info',return_value=self.owner),patch.object(control.time,'monotonic',return_value=now),patch.object(control,'fetch_control',return_value=value) as fetch,patch.dict(os.environ,{'GH_TOKEN':'PRIVATE_FIXTURE','GITHUB_REPOSITORY':'owner/repo'}),redirect_stdout(output):
            control.receive(root,stage)
        return fetch,json.loads(output.getvalue())
    def test_exact_total_is_900_seconds_from_original_kernel_start(self):
        self.assertEqual(control.UI_BUDGET_SECONDS,900)
        self.assertEqual(control.checked_budget(self.record,900,self.owner),1000)
    def test_old_expanded_or_wrong_typed_budget_is_rejected(self):
        for seconds in (300,901,1800,3600,True,'900',900.0):
            with self.subTest(seconds=seconds):
                record={**self.record,'budget_seconds':seconds}
                with self.assertRaises(ValueError):control.checked_budget(record,900,self.owner)
    def test_three_stages_share_original_deadline_past_old_300_seconds(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);session.put(root/'ui-deadline.json',self.record)
            original=(root/'ui-deadline.json').read_bytes()
            for stage,now in ((1,350),(2,700),(3,999)):
                request=self.prepare(root,stage);fetch,diagnostic=self.receive(root,stage,now,request)
                self.assertEqual(json.loads((root/f'stage-{stage}/control.json').read_bytes()),request)
                self.assertEqual(diagnostic,{'event':'UI_APPROVAL_WAIT','stage':stage,'budget_seconds':900,'remaining_seconds':1000-now})
                self.assertNotIn('PRIVATE_FIXTURE',json.dumps(diagnostic))
                self.assertEqual((root/'ui-deadline.json').read_bytes(),original)
                self.assertLessEqual(fetch.call_args.args[-1],1000-now)
    def test_exact_and_later_deadline_never_fetches_or_writes(self):
        for now in (1000,1001):
            with self.subTest(now=now),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);session.put(root/'ui-deadline.json',self.record);self.prepare(root,2)
                with patch.object(session,'process_info',return_value=self.owner),patch.object(control.time,'monotonic',return_value=now),patch.object(control,'fetch_control') as fetch,redirect_stdout(io.StringIO()):
                    with self.assertRaises(TimeoutError):control.receive(root,2)
                fetch.assert_not_called();self.assertFalse((root/'stage-2/control.json').exists())
    def test_control_returning_at_deadline_is_not_consumed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);session.put(root/'ui-deadline.json',self.record);request=self.prepare(root,2)
            clock=[999.0]
            def late(*_):clock[0]=1000.0;return request
            with patch.object(session,'process_info',return_value=self.owner),patch.object(control.time,'monotonic',side_effect=lambda:clock[0]),patch.object(control,'fetch_control',side_effect=late),patch.dict(os.environ,{'GH_TOKEN':'fixture','GITHUB_REPOSITORY':'owner/repo'}),redirect_stdout(io.StringIO()):
                with self.assertRaises(TimeoutError):control.receive(root,2)
            self.assertFalse((root/'stage-2/control.json').exists())
    def test_absent_control_expires_without_stage_reset(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);session.put(root/'ui-deadline.json',self.record);self.prepare(root,3)
            clock=[998.0]
            def advance(seconds):clock[0]+=seconds
            with patch.object(session,'process_info',return_value=self.owner),patch.object(control.time,'monotonic',side_effect=lambda:clock[0]),patch.object(control.time,'sleep',side_effect=advance),patch.object(control,'fetch_control',return_value=None) as fetch,patch.dict(os.environ,{'GH_TOKEN':'fixture','GITHUB_REPOSITORY':'owner/repo'}),redirect_stdout(io.StringIO()):
                with self.assertRaises(TimeoutError):control.receive(root,3)
            self.assertEqual(clock[0],1000);fetch.assert_called_once()
            self.assertFalse((root/'stage-3/control.json').exists())
    def test_repeated_ui_reads_cannot_refresh_original_deadline(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);session.put(root/'ui-deadline.json',self.record)
            with patch.object(session,'process_info',return_value=self.owner):
                for now in (100,450,999,1001):
                    with patch.object(control.time,'monotonic',return_value=now):self.assertEqual(control.read_ui_deadline(root),1000)
    def test_initial_wait_and_enclosing_and_individual_limits_are_preserved(self):
        import yaml
        workflow=yaml.safe_load((BASE.parents[1]/'.github/workflows/academy-official.yml').read_text())
        waits=[step for step in workflow['jobs']['package']['steps'] if 'ui_control.py' in step.get('run','')]
        self.assertEqual(len(waits),3);self.assertTrue(all(step['timeout-minutes']==5 for step in waits))
        source=(BASE/'ui_session.py').read_text()
        self.assertIn('while time.monotonic()<started+30:',source)
        self.assertIn('owned=Owned(started+2700)',source)
        self.assertEqual(source.count("put(root/'ui-deadline.json',record)"),1)
        self.assertIn("put(root/'state.json',budget_record(owner,3600))",source)
        self.assertIn("2700,root,phase='validate'",(BASE/'run_official.py').read_text())

class WorkflowTest(unittest.TestCase):
    def setUp(self):
        self.workflow=(BASE.parents[1]/'.github/workflows/academy-official.yml').read_text()
        self.runner=(BASE/'run_official.py').read_text()
        self.helper=(BASE/'probes/AgreementUi.java').read_text()
    def test_original_budgets(self):
        self.assertIn('&& 85 || 30',self.workflow);self.assertIn('timeout-minutes: 65',self.workflow)
        self.assertIn("2700,root,phase='validate'",self.runner)
        self.assertIn('ui_deadline=started+UI_BUDGET_SECONDS',(BASE/'ui_session.py').read_text())
    def test_source_gate_still_exact(self):
        self.assertIn('check_source_ci.py --report',self.workflow)
        self.assertIn("ci.get('sha')==os.environ.get('GITHUB_SHA')",self.runner)
    def test_environment_release_gate_unchanged(self):
        self.assertIn('timeout-minutes: 50',self.workflow)
        self.assertIn("steps.environment.outcome == 'success' && steps.release_gate.outcome == 'success'",self.workflow)
        self.assertIn('scripts/academy/release_gate.py',self.workflow)
    def test_all_three_artifacts_and_finite_actions(self):
        for stage in (1,2,3):self.assertIn(f'academy-ui-stage-{stage}-',self.workflow)
        for action in control.ACTIONS.values():self.assertIn(f'case "{action}"',self.helper)
        self.assertNotIn('Integer.parseInt',self.helper)
    def test_fresh_home_no_acceptance_write(self):
        self.assertIn("'config','system','log','tmp','home'",self.runner)
        self.assertIn('-Duser.home=',self.runner)
        self.assertNotIn('eua_accepted_version',self.runner)
        self.assertNotIn('eua_accepted_version',(BASE/'ui_session.py').read_text())
    def test_original_tests_and_links(self):
        self.assertIn("'--tests','true','--links','true'",self.runner)
        self.assertIn('inspect_import(validation,contract',self.runner)
    def test_screenshot_match_before_click(self):
        self.assertLess(self.helper.index('equals(args[2])'),self.helper.index('robot.mousePress'))
    def test_telemetry_accept_not_implemented(self):self.assertNotIn('SEND_USAGE',self.helper)

if __name__=='__main__':unittest.main()
