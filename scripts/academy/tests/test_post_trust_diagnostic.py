"""Owned-observer mocks and real file boundaries; never a GUI or JVM attach."""
import copy,json,os,subprocess,sys,unittest,time
from contextlib import ExitStack
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
        self.owner={'pid':99,'ppid':98,'uid':os.getuid(),'pgrp':99,'session':99,'start_time':'0'}
        self.meta={'pid':100,'ppid':99,'uid':os.getuid(),'pgrp':100,'session':100,'start_time':'0'}
        binding=''.join('ide.'+k+'='+str(v)+'\n' for k,v in self.meta.items())
        (self.root/'display-binding.properties').write_text(binding)
        self.request['display_binding_sha256']=diagnostic.digest(binding.encode())
        self.approval={**copy.deepcopy(self.request),'visual_review':copy.deepcopy(__import__('project_trust').REVIEW)}
        self.write(self.root/'stage-4/request.json',self.request);(self.root/'stage-4/after.png').write_bytes(self.image)
        self.write(self.root/'stage-4/receipt.json',{**self.approval,'after_sha256':diagnostic.digest(self.image),'status':'UI_ACTION_PERFORMED_NOT_COURSE_ACCEPTANCE'})
        self.owner_probe=patch.object(ui_session,'process_info',return_value=self.owner);self.owner_probe.start();self.addCleanup(self.owner_probe.stop)
        self.live_probe=patch.object(ui_control,'checked_live_budget',side_effect=lambda record,seconds:ui_control.checked_budget(record,seconds,ui_session.process_info(record['owner']['pid'])));self.live_probe.start();self.addCleanup(self.live_probe.stop)
        ui_session.put(self.root/'ui-deadline.json',ui_session.budget_record(self.owner,900))
        with patch.object(diagnostic.time,'monotonic',return_value=100):diagnostic.bind_budget_owner(self.root)
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
        source=(repo/'scripts/academy/restart_session.py').read_text();self.assertIn('observer.tick(current,screen,identity)',source)
        self.assertNotIn('jcmd',source);self.assertNotIn('jps',source)
    def test_diagnostic_state_cannot_satisfy_release_gate(self):
        from release_gate import evaluate
        from gates import GateError
        for status in diagnostic.STATUSES:
            with self.assertRaises(GateError):evaluate({'status':status,'native_archive_verified':True})
    def test_observer_cancellation_reaches_existing_owned_cleanup(self):
        from test_restart_session import run_fixture
        code,value,family,identity,_=run_fixture('observer')
        self.assertEqual(code,1);self.assertTrue(value['cancelled'])
        family.close.assert_called_once();family.begin_validation.assert_not_called()


class BudgetBindingTests(ObserverFixture):
    def test_owner_receipt_is_one_use_and_cannot_reset_budget(self):
        before=(self.root/diagnostic.BUDGET_OWNER).read_bytes()
        with patch.object(diagnostic.time,'monotonic',return_value=100),self.assertRaises(FileExistsError):diagnostic.bind_budget_owner(self.root)
        self.assertEqual((self.root/diagnostic.BUDGET_OWNER).read_bytes(),before)

    def test_wrong_owner_is_rejected_at_creation(self):
        (self.root/diagnostic.BUDGET_OWNER).unlink()
        record=ui_session.budget_record({**self.owner,'pid':97},900);self.write(self.root/'ui-deadline.json',record)
        with patch.object(diagnostic.time,'monotonic',return_value=100),self.assertRaises(ValueError):diagnostic.bind_budget_owner(self.root)
        self.assertFalse((self.root/diagnostic.BUDGET_OWNER).exists())

    def test_changed_owner_birth_is_rejected_before_anchor(self):
        self.owner_probe.stop()
        with patch.object(ui_session,'process_info',return_value={**self.owner,'start_time':'1'}),self.assertRaises(ValueError):self.observer()
        self.assertFalse((self.root/diagnostic.ANCHOR).exists())

    def test_expired_original_owner_cannot_initialize_observer(self):
        with self.assertRaises(ValueError):self.observer(start=900)
        self.assertFalse((self.root/diagnostic.ANCHOR).exists());self.screen.assert_not_called()

    def test_supplied_deadline_cannot_replace_fixed_original(self):
        for value in (901,1000,3600,True,float('nan')):
            with self.subTest(value=value),self.assertRaises(ValueError):self.observer(ui=value)
        self.assertFalse((self.root/diagnostic.ANCHOR).exists())

    def test_changed_budget_bytes_are_rejected_after_capture(self):
        self.capture_fallback();record=diagnostic.raw_json(self.root/'ui-deadline.json');record['monotonic_deadline']+=1
        self.write(self.root/'ui-deadline.json',record)
        with self.assertRaises(ValueError):diagnostic.collect(self.root,'123','1')

    def test_collector_rejects_recomputed_ide_or_arbitrary_deadline(self):
        report=self.capture_fallback();anchor=diagnostic.raw_json(self.root/diagnostic.ANCHOR)
        anchor['ui_deadline']+=1;raw=diagnostic.encode(anchor);(self.root/diagnostic.ANCHOR).write_bytes(raw)
        report['anchor_sha256']=diagnostic.digest(raw);self.write(self.root/diagnostic.REPORT,report)
        with self.assertRaises(ValueError):diagnostic.collect(self.root,'123','1')

    def test_wrong_gui_parent_and_older_gui_birth_are_rejected(self):
        budget,_=diagnostic.checked_budget_owner(self.root)
        with self.assertRaises(ValueError):diagnostic.owner_matches_gui(budget,{**self.meta,'ppid':98})
        newer=copy.deepcopy(budget);newer['record']['owner']['start_time']='10'
        with self.assertRaises(ValueError):diagnostic.owner_matches_gui(newer,self.meta)

    def test_budget_schema_refuses_nested_private_fields_and_type_confusion(self):
        budget,_=diagnostic.checked_budget_owner(self.root)
        for changes in ({'schema_version':True},{'kind':'IDE_BUDGET'},{'record_sha256':{'secret':'PRIVATE'}},{'environment':{'secret':'PRIVATE'}}):
            with self.assertRaises(ValueError):diagnostic.budget_document({**budget,**changes})
        for key in ('pid','ppid','start_time'):
            bad=copy.deepcopy(budget);bad['record']['owner'][key]=True
            with self.assertRaises(ValueError):diagnostic.budget_document(bad)

    def test_native_collector_retains_budget_when_later_report_is_invalid(self):
        from collect_evidence import collect
        self.capture_fallback();(self.root/diagnostic.REPORT).write_bytes(b'{"environment":{"TOKEN":"PRIVATE_FIXTURE"}}')
        (self.run/'evidence/validate.stderr.log').write_text('safe fixture log\n')
        output=self.temp/'native-evidence';collect(self.run,output,ui_root=self.root,job_status='failure',cleanup_exit=0)
        budget=diagnostic.budget_document(json.loads((output/diagnostic.BUDGET_OWNER).read_bytes()))
        self.assertEqual(budget['record']['owner'],self.owner)
        self.assertFalse((output/diagnostic.REPORT).exists());self.assertTrue((output/'validate.stderr.log').exists())
        for path in output.iterdir():self.assertNotIn(b'PRIVATE_FIXTURE',path.read_bytes())

    def test_invalid_budget_cannot_enter_native_evidence(self):
        from collect_evidence import collect
        self.write(self.root/diagnostic.BUDGET_OWNER,{'command':{'environment':'PRIVATE_FIXTURE'}})
        (self.run/'evidence/validate.stderr.log').write_text('safe fixture log\n')
        output=self.temp/'native-evidence';collect(self.run,output,ui_root=self.root,job_status='failure',cleanup_exit=0)
        self.assertFalse((output/diagnostic.BUDGET_OWNER).exists());self.assertTrue((output/'validate.stderr.log').exists())
        for path in output.iterdir():self.assertNotIn(b'PRIVATE_FIXTURE',path.read_bytes())

    def test_owner_receipt_symlink_is_not_followed(self):
        self.capture_fallback();path=self.root/diagnostic.BUDGET_OWNER;path.rename(self.root/'other-budget.json');path.symlink_to(self.root/'other-budget.json')
        with self.assertRaises(OSError):diagnostic.collect(self.root,'123','1')


class ComposedOwnerHandoffTests(TrustFixture):
    """Real harmless parent/child births and files; mocked pixels/PDF/JAR/X11 only."""
    def test_real_dead_owner_rejects_live_observer_but_preserves_historical_receipt(self):
        from test_ui_session import real_budget_owner
        with real_budget_owner(self.root,bind_receipt=True) as (child,fd,exit_unreaped):
            before=(self.root/diagnostic.BUDGET_OWNER).read_bytes()
            value,_=diagnostic.checked_budget_owner(self.root,live=True)
            exit_unreaped();self.assertFalse(ui_session.live(fd))
            with self.assertRaises(ValueError):diagnostic.checked_budget_owner(self.root,live=True)
            self.assertEqual(json.loads(diagnostic.collect_budget_owner(self.root,'123','1')),value)
            self.assertEqual(child.wait(timeout=3),0)
            with self.assertRaises(ProcessLookupError):diagnostic.checked_budget_owner(self.root,live=True)
            self.assertEqual(json.loads(diagnostic.collect_budget_owner(self.root,'123','1')),value)
            self.assertEqual((self.root/diagnostic.BUDGET_OWNER).read_bytes(),before)

    def test_actual_owner_anchor_collector_and_stage5_use_one_deadline(self):
        import plugin_agreement as plugin
        owner=ui_session.process_info(os.getpid());record=ui_session.budget_record(owner,900)
        ui_session.put(self.root/'ui-deadline.json',record);diagnostic.bind_budget_owner(self.root)
        time.sleep(.02)  # Ensure a distinct actual Linux start tick; no IDE is launched.
        child=subprocess.Popen([sys.executable,'-B','-c','import sys;sys.stdin.buffer.read()'],stdin=subprocess.PIPE,
                               stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        fd=None
        try:
            meta=ui_session.process_info(child.pid);fd=os.pidfd_open(child.pid)
            self.assertGreater(int(meta['start_time']),int(owner['start_time']))
            self.assertEqual(meta['ppid'],owner['pid'])
            binding=''.join('ide.'+key+'='+str(value)+'\n' for key,value in meta.items())
            (self.root/'display-binding.properties').write_text(binding)
            self.request['window_identity']['pid']=child.pid
            self.request['display_binding_sha256']=diagnostic.digest(binding.encode())
            self.approval={**copy.deepcopy(self.request),'visual_review':copy.deepcopy(__import__('project_trust').REVIEW)}
            self.stage();(self.root/'stage-4/after.png').write_bytes(self.image)
            self.write(self.root/'stage-4/receipt.json',{**self.approval,'after_sha256':diagnostic.digest(self.image),'status':plugin.STATUS})
            identity=type('FixtureIdentity',(),{})();identity.metadata={'ide':meta};identity.binding=self.root/'display-binding.properties'
            def verify():
                self.assertTrue(ui_session.matching(meta,fd));self.assertEqual(ui_session.process_info(owner['pid']),owner)
            identity.verify=verify
            now=time.monotonic();wall=time.time_ns();clock=[now]
            directory=self.run/'validate-profile/log/bg-wa';directory.mkdir(parents=True)
            actions=[]
            def screen(action,path,*args,**kwargs):
                verify();actions.append(action);path.write_bytes(self.image)
                if action in plugin.ACTIONS.values():Path(args[1]).write_text(action+'\n')
            with patch.object(diagnostic.time,'monotonic',side_effect=lambda:clock[0]),patch.object(diagnostic.time,'time_ns',return_value=wall):
                observer=diagnostic.Observer(self.root,identity,record['monotonic_deadline'])
                clock[0]+=60;observer.tick(child,screen,identity)
                self.assertTrue(observer.done)
                diagnostic.wait_collect(self.root,'123','1')  # Actual strict collector, not mocked.
                report=diagnostic.raw_json(self.root/'post-trust-artifact'/diagnostic.REPORT)
                self.assertEqual(report['budget_owner']['record'],record)
                self.assertNotEqual(record['monotonic_deadline'],int(meta['start_time'])/os.sysconf('SC_CLK_TCK')+900)
                original=plugin.publish;owned=type('FixtureOwned',(),{'scan':lambda _self:verify()})()
                def publish(path,raw):
                    original(path,raw)
                    if path.name=='request.json':
                        approved={**json.loads(raw),'visual_review':plugin.review(5)}
                        with patch.object(plugin,'fetch_control',return_value=approved):plugin.receive(self.root,5)
                window={'window_id':56,'pid':child.pid,'x':380,'y':335,'width':520,'height':235,'border':0,'title_sha256':'e'*64}
                idea=self.temp/'idea';command=[str(idea/'bin/idea'),'validateCourse',str(self.run/'validation'),'--archive',str(self.archive),
                    '--tests','true','--links','true','--output-format','json','--output',str(self.run/'evidence/official-validation.json')]
                before=(self.root/'ui-deadline.json').read_bytes()
                with patch.object(plugin,'verify_plugin',return_value=plugin.PLUGIN_SHA),patch.object(plugin,'verify_legal',return_value=plugin.LEGAL_ID),patch.object(plugin,'window_probe',return_value=window),patch.object(plugin,'publish',side_effect=publish):
                    plugin.checkpoint(self.root,5,child,screen,identity,owned,ui_control.read_ui_deadline(self.root),command,idea,{})
                receipt=plugin.collect(self.root,5,'123','1')['plugin-stage-5-receipt.json']
                self.assertEqual(json.loads(receipt)['status'],plugin.STATUS)
                self.assertEqual(actions,['SNAPSHOT','SNAPSHOT',plugin.ACTIONS[5]])
                self.assertEqual((self.root/'ui-deadline.json').read_bytes(),before)
                self.assertEqual(ui_control.read_ui_deadline(self.root),record['monotonic_deadline'])
                # Same PID with a different birth must fail every live deadline consumer.
                with patch.object(ui_session,'process_info',return_value={**owner,'start_time':str(int(owner['start_time'])+1)}),self.assertRaises(ValueError):ui_control.read_ui_deadline(self.root)
        finally:
            if child.stdin:child.stdin.close()
            try:code=child.wait(timeout=2)
            except subprocess.TimeoutExpired:
                child.terminate();child.wait(timeout=2);self.fail('fixture child did not exit normally')
            finally:
                if fd is not None:os.close(fd)
            self.assertEqual(code,0)

if __name__=='__main__':unittest.main()
