"""Owned-observer mocks and real file boundaries; never a GUI or JVM attach."""
import copy,json,os,subprocess,sys,unittest
from pathlib import Path
from unittest.mock import Mock,patch,MagicMock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import post_trust_diagnostic as diagnostic
import post_trust_stacks as stacks
import ui_control,ui_session
from test_project_trust import TrustFixture
from test_display_diagnostic import png

class ObserverFixture(TrustFixture):
    def setUp(self):
        super().setUp();self.stage();self.wall=10**18
        self.meta={'pid':100,'ppid':99,'uid':os.getuid(),'pgrp':100,'session':100,'start_time':'0'}
        binding=''.join('ide.'+k+'='+str(v)+'\n' for k,v in self.meta.items())
        (self.root/'display-binding.properties').write_text(binding)
        self.request['display_binding_sha256']=diagnostic.digest(binding.encode())
        self.approval={**copy.deepcopy(self.request),'visual_review':copy.deepcopy(__import__('project_trust').REVIEW)}
        self.write(self.root/'stage-4/request.json',self.request);(self.root/'stage-4/after.png').write_bytes(self.image)
        self.write(self.root/'stage-4/receipt.json',{**self.approval,'after_sha256':diagnostic.digest(self.image),'status':'UI_ACTION_PERFORMED_NOT_COURSE_ACCEPTANCE'})
        self.identity=Mock();self.identity.metadata={'ide':self.meta};self.identity.binding=self.root/'display-binding.properties'
        self.proc=Mock();self.proc.poll.return_value=None
        self.directory=self.run/'validate-profile/log/bg-wa';self.directory.mkdir(parents=True)
        self.screen=Mock(side_effect=lambda action,path,**kwargs:path.write_bytes(png()))
    def observer(self,start=100,ui=900):
        with patch.object(diagnostic.time,'monotonic',return_value=start),patch.object(diagnostic.time,'time_ns',return_value=self.wall):
            return diagnostic.Observer(self.root,self.identity,ui)
    def tick(self,observer,now,wall=None):
        with patch.object(diagnostic.time,'monotonic',return_value=now),patch.object(diagnostic.time,'time_ns',return_value=wall or self.wall+int((now-100)*1e9)):
            observer.tick(self.proc,self.screen,self.identity)
    def dump(self,number=1,when=None):
        p=self.directory/f'thread-dump-{number}.txt';p.write_bytes(b'"AWT-EventQueue-0"\n   java.lang.Thread.State: WAITING\n\tat java.lang.Thread.run(Thread.java:1)\n\n')
        os.utime(p,ns=(when or self.wall+1,when or self.wall+1));return p
    def capture_fallback(self):
        obj=self.observer();self.tick(obj,160);return diagnostic.raw_json(self.root/diagnostic.REPORT)

class ObserverTests(ObserverFixture):
    def test_first_stable_post_trust_file_captures_once(self):
        obj=self.observer();self.dump();self.tick(obj,100,wall=self.wall+2);self.assertFalse(obj.done)
        self.tick(obj,101,wall=self.wall+3);self.assertTrue(obj.done)
        report=diagnostic.raw_json(self.root/diagnostic.REPORT)
        self.assertEqual(report['capture_trigger'],'FIRST_STABLE_POST_TRUST');self.assertEqual(report['scan_count'],2)
        self.assertEqual(report['status'],'COLLECTED_NOT_ACCEPTANCE');self.assertEqual(report['stacks']['samples'][0]['source_id'],1)
        self.assertEqual(self.screen.call_count,1);self.assertEqual(self.screen.call_args.kwargs['diagnostic_deadline'],190)
        self.tick(obj,102);self.assertEqual(self.screen.call_count,1)
    def test_no_new_dump_falls_back_at_sixty_seconds(self):
        obj=self.observer();self.dump(2,self.wall-1);self.tick(obj,159);self.assertFalse(obj.done)
        self.tick(obj,160);report=diagnostic.raw_json(self.root/diagnostic.REPORT)
        self.assertEqual(report['capture_trigger'],'FALLBACK_60_SECONDS');self.assertEqual(report['stacks']['samples'],[])
        self.assertEqual(report['status'],'PARTIAL_NOT_ACCEPTANCE');self.assertEqual(report['screenshot_status'],'CAPTURED_NOT_ACCEPTANCE')
    def test_polling_does_not_reset_deadline_or_scan_too_often(self):
        obj=self.observer()
        with patch.object(stacks,'scan',wraps=stacks.scan) as scan:
            for now in (100,100.1,100.2,100.99,101):self.tick(obj,now)
            self.assertEqual(scan.call_count,2)
        self.assertEqual(obj.deadline,190)
    def test_exact_ninety_second_deadline_starts_no_read_or_screenshot(self):
        obj=self.observer()
        with patch.object(stacks,'scan') as scan,patch.object(stacks,'capture') as capture:self.tick(obj,190)
        scan.assert_not_called();capture.assert_not_called();self.screen.assert_not_called()
        report=diagnostic.raw_json(self.root/diagnostic.REPORT);self.assertEqual(report['capture_trigger'],'OBSERVER_DEADLINE');self.assertEqual(report['elapsed_seconds'],90)
    def test_late_tick_records_delay_without_authorizing_late_capture(self):
        obj=self.observer();self.tick(obj,205);self.screen.assert_not_called()
        report=diagnostic.raw_json(self.root/diagnostic.REPORT);self.assertEqual(report['elapsed_seconds'],105);self.assertEqual(report['status'],'UNAVAILABLE_NOT_ACCEPTANCE')
    def test_existing_ui_deadline_clips_the_observer(self):
        obj=self.observer(start=870);self.assertEqual(obj.deadline,900);self.tick(obj,900);self.screen.assert_not_called()
    def test_exit_before_capture_keeps_passive_metadata_without_screen(self):
        obj=self.observer();self.proc.poll.return_value=1;self.tick(obj,105)
        self.screen.assert_not_called();report=diagnostic.raw_json(self.root/diagnostic.REPORT);self.assertEqual(report['capture_trigger'],'IDE_EXITED');self.assertEqual(report['screenshot_status'],'UNAVAILABLE_IDE_EXITED')
    def test_scan_failure_still_attempts_owned_screenshot(self):
        obj=self.observer()
        with patch.object(stacks,'scan',side_effect=OSError('PRIVATE_FIXTURE')):self.tick(obj,101)
        report=diagnostic.raw_json(self.root/diagnostic.REPORT);self.assertEqual(report['screenshot_status'],'CAPTURED_NOT_ACCEPTANCE');self.assertNotIn('PRIVATE_FIXTURE',json.dumps(report))
    def test_cancellation_during_scan_is_not_swallowed(self):
        obj=self.observer()
        with patch.object(stacks,'scan',side_effect=InterruptedError),self.assertRaises(InterruptedError):self.tick(obj,101)
        self.assertFalse((self.root/diagnostic.REPORT).exists());self.screen.assert_not_called()
    def test_cancellation_during_snapshot_is_not_swallowed(self):
        obj=self.observer();self.screen.side_effect=InterruptedError
        with self.assertRaises(InterruptedError):self.tick(obj,160)
        self.assertFalse((self.root/diagnostic.REPORT).exists())
    def test_changed_owned_identity_prevents_snapshot(self):
        obj=self.observer();self.identity.metadata={'ide':{**self.meta,'start_time':'1'}};self.tick(obj,160)
        self.screen.assert_not_called();report=diagnostic.raw_json(self.root/diagnostic.REPORT);self.assertEqual(report['screenshot_status'],'UNAVAILABLE_IDENTITY_OR_CAPTURE')

class BoundaryTests(ObserverFixture):
    def test_current_bound_receipt_and_sanitized_image_collect(self):
        self.capture_fallback();files=diagnostic.collect(self.root,'123','1')
        self.assertEqual(set(files),{diagnostic.REPORT,diagnostic.PNG,diagnostic.MAPPING});self.assertNotIn(b'PRIVATE_METADATA',files[diagnostic.PNG])
        self.assertEqual(json.loads(files[diagnostic.MAPPING])['uploaded_sha256'],diagnostic.digest(files[diagnostic.PNG]))
    def test_wrong_run_attempt_and_replaced_anchor_refused(self):
        self.capture_fallback()
        with self.assertRaises(ValueError):diagnostic.collect(self.root,'123','2')
        anchor=diagnostic.raw_json(self.root/diagnostic.ANCHOR);anchor['anchor_wall_ns']+=1;self.write(self.root/diagnostic.ANCHOR,anchor)
        with self.assertRaises(ValueError):diagnostic.collect(self.root,'123','1')
    def test_mismatched_process_birth_metadata_refused(self):
        report=self.capture_fallback();report['ui_identity']['start_time']='1';self.write(self.root/diagnostic.REPORT,report)
        with self.assertRaises(ValueError):diagnostic.collect(self.root,'123','1')
    def test_nested_extra_and_boolean_numeric_metadata_refused(self):
        report=self.capture_fallback()
        for bad in [{**report,'environment':{'TOKEN':'PRIVATE_FIXTURE'}},{**report,'anchor_wall_ns':True},{**report,'capture_trigger':{'secret':'PRIVATE_FIXTURE'}},{**report,'ui_identity':{**report['ui_identity'],'pid':True}},{**report,'elapsed_seconds':float('nan')}]:
            with self.assertRaises(ValueError):diagnostic.validate_document(bad)
    def test_unavailable_stack_or_screen_cannot_claim_complete_diagnostic(self):
        report=self.capture_fallback();self.assertEqual(report['status'],'PARTIAL_NOT_ACCEPTANCE')
        with self.assertRaises(ValueError):diagnostic.validate_document({**report,'status':'COLLECTED_NOT_ACCEPTANCE'})
    def test_duplicate_and_oversized_json_refused(self):
        self.capture_fallback();p=self.root/diagnostic.REPORT;p.write_bytes(b'{"schema_version":1,"schema_version":1}')
        with self.assertRaises(ValueError):diagnostic.collect(self.root,'123','1')
        p.write_bytes(b'x'*(diagnostic.MAX_REPORT+1))
        with self.assertRaises(ValueError):diagnostic.collect(self.root,'123','1')
    def test_report_and_image_symlinks_refused(self):
        self.capture_fallback();p=self.root/diagnostic.PNG;p.rename(self.root/'elsewhere.png');p.symlink_to(self.root/'elsewhere.png')
        with self.assertRaises(OSError):diagnostic.collect(self.root,'123','1')
    def test_old_output_directory_is_not_reused(self):
        out=self.root/'post-trust-artifact';out.mkdir();(out/diagnostic.REPORT).write_bytes(b'OLD')
        with self.assertRaises(FileExistsError):diagnostic.wait_collect(self.root,'123','1')
        self.assertEqual((out/diagnostic.REPORT).read_bytes(),b'OLD')
    def test_completed_observation_can_stage_after_owner_exit(self):
        self.capture_fallback()
        with patch.object(ui_control,'read_ui_deadline',side_effect=FileNotFoundError) as clock:
            diagnostic.wait_collect(self.root,'123','1');clock.assert_not_called()
        self.assertTrue((self.root/'post-trust-artifact'/diagnostic.REPORT).is_file())
    def test_waiter_uses_original_anchor_deadline(self):
        self.observer()
        with patch.object(ui_control,'read_ui_deadline',return_value=900),patch.object(diagnostic.time,'monotonic',return_value=191),patch.object(diagnostic.time,'sleep') as sleep:
            with self.assertRaises(TimeoutError):diagnostic.wait_collect(self.root,'123','1')
            sleep.assert_not_called()
    def test_waiter_and_collector_cancellation_propagates(self):
        self.observer()
        with patch.object(ui_control,'read_ui_deadline',return_value=900),patch.object(diagnostic.time,'monotonic',return_value=180),patch.object(diagnostic.time,'sleep',side_effect=InterruptedError),self.assertRaises(InterruptedError):diagnostic.wait_collect(self.root,'123','1')
    def test_real_workflow_failure_sets_no_upload_marker(self):
        import yaml
        repo=Path(diagnostic.__file__).parents[2];workflow=yaml.safe_load((repo/'.github/workflows/academy-official.yml').read_text());step=next(s for s in workflow['jobs']['package']['steps'] if s.get('id')=='post_trust_diagnostic')
        out=self.root/'post-trust-artifact';out.mkdir();(out/diagnostic.REPORT).write_bytes(b'OLD')
        marker=self.temp/'step-output';env=dict(os.environ,PATH=str(Path(sys.executable).parent)+os.pathsep+os.defpath,UI_RUN=str(self.root),GITHUB_OUTPUT=str(marker))
        run=subprocess.run(['bash','-e','-c',step['run']],cwd=repo,env=env,capture_output=True,timeout=10)
        self.assertEqual(run.returncode,1);self.assertIn(b'FileExistsError',run.stderr);self.assertFalse(marker.exists());self.assertEqual((out/diagnostic.REPORT).read_bytes(),b'OLD')

class IntegrationTests(unittest.TestCase):
    def test_snapshot_subprocess_deadline_cannot_extend_owner_or_observer(self):
        with patch.object(ui_session.time,'monotonic',return_value=100):
            self.assertEqual(ui_session.snapshot_timeout(900,105),5)
            for deadline in (100,99):
                with self.assertRaises(TimeoutError):ui_session.snapshot_timeout(900,deadline)
            for deadline in (901,True,float('nan'),'105'):
                with self.assertRaises(ValueError):ui_session.snapshot_timeout(900,deadline)
    def test_success_marker_gates_only_exact_projected_artifact_files(self):
        import yaml
        repo=Path(diagnostic.__file__).parents[2];workflow=yaml.safe_load((repo/'.github/workflows/academy-official.yml').read_text());steps=workflow['jobs']['package']['steps']
        upload=next(s for s in steps if s.get('id')=='post_trust_upload');self.assertIn("steps.post_trust_diagnostic.outputs.collected == 'true'",upload['if'])
        self.assertEqual(upload['with']['path'].splitlines(),['${{ env.UI_RUN }}/post-trust-artifact/'+name for name in (diagnostic.REPORT,diagnostic.PNG,diagnostic.MAPPING)])
        self.assertEqual(upload['with']['retention-days'],1)
        self.assertEqual(ui_control.UI_BUDGET_SECONDS,900)
        source=(repo/'scripts/academy/ui_session.py').read_text();self.assertIn('post_trust_observer.tick(proc,screen,identity)',source)
        self.assertNotIn('jcmd',source);self.assertNotIn('jps',source)
    def test_diagnostic_state_cannot_satisfy_release_gate(self):
        from release_gate import evaluate
        from gates import GateError
        for status in diagnostic.STATUSES:
            with self.assertRaises(GateError):evaluate({'status':status,'native_archive_verified':True})
    def test_observer_cancellation_reaches_existing_owned_cleanup(self):
        import hashlib,tempfile
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);jar=MagicMock();jar.__enter__.return_value=jar;jar.getinfo.return_value.file_size=7;jar.read.return_value=b'fixture'
            proc=Mock();proc.pid=100;proc.poll.return_value=None;proc.wait.return_value=-15
            owned=Mock();owned.members={100:({'pid':100},9)};owned.register_root.return_value={'pid':100,'start_time':'0','uid':0,'session':100,'pgrp':100}
            identity=Mock();identity.metadata={'fixture':True};identity.handles={};identity.binding=root/'binding'
            observer=Mock();observer.tick.side_effect=InterruptedError('cancelled')
            clock=[0];original=ui_session.put
            def now():clock[0]+=1;return clock[0]
            def put(path,value):
                original(path,value)
                if path.name=='request.json':original(path.with_name('control.json'),value)
            def screen_command(args,**kwargs):Path(args[6]).write_bytes(b'SYNTHETIC_PNG')
            with patch.dict(os.environ,{'GITHUB_RUN_ID':'123','GITHUB_RUN_ATTEMPT':'1'}),patch.object(ui_session,'trust_context'),patch.object(ui_session.zipfile,'ZipFile',return_value=jar),patch.object(ui_session,'EUA_SHA256',hashlib.sha256(b'fixture').hexdigest()),patch.object(ui_control,'EUA_SHA256',hashlib.sha256(b'fixture').hexdigest()),patch.object(ui_session,'Owned',return_value=owned),patch.object(ui_session,'DisplayIdentity',return_value=identity),patch.object(ui_session.subprocess,'Popen',return_value=proc),patch.object(ui_session.subprocess,'run',side_effect=screen_command),patch.object(ui_session.signal,'signal'),patch.object(ui_session.time,'monotonic',side_effect=now),patch.object(ui_session.time,'sleep'),patch.object(ui_session,'put',side_effect=put),patch.object(ui_session,'capture_display_diagnostic',return_value=None),patch.object(ui_session,'trust_checkpoint'),patch.object(ui_session,'PostTrustObserver',return_value=observer):
                with self.assertRaises(InterruptedError):ui_session.display_session(root,root,['fixture'])
            owned.stop.assert_called_once();identity.close.assert_called_once();proc.wait.assert_called_once()

if __name__=='__main__':unittest.main()
