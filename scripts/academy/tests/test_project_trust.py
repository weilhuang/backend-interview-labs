"""Synthetic schemas and owned-flow mocks; no real GUI approval or trust is exercised."""
import copy,json,os,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import Mock,patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import project_trust as trust
import trust_window as window
import ui_control,ui_session
from test_display_diagnostic import png

class TrustFixture(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.temp=Path(self.tmp.name)
        self.root=self.temp/'academy-ui-123-1';self.root.mkdir();self.run=self.temp/'academy-run-123-1';self.run.mkdir();(self.run/'evidence').mkdir()
        (self.root/'stage-3').mkdir();self.stage3={'run_id':'123','run_attempt':'1','stage':3,'action':'DECLINE_USAGE','status':'UI_ACTION_PERFORMED_NOT_ACCEPTANCE'}
        self.write(self.root/'stage-3/receipt.json',self.stage3);(self.root/'display-binding.properties').write_bytes(b'owned synthetic display')
        self.archive=self.run/'backend-interview-academy.zip';self.archive.write_bytes(b'synthetic archive')
        self.ci={'status':'PASS','sha':'a'*40,'tested_sha':'a'*40,'commit_tree':'b'*40}
        self.generation={'status':'PASS','full_manifest_sha256':trust.SOURCE_MANIFEST,**trust.COUNTS}
        self.summary={'commit':'a'*40,'run_id':'123','run_attempt':'1','repository':'weilhuang/backend-interview-labs'}
        self.write(self.run/'evidence/source-ci.json',self.ci);self.write(self.run/'evidence/generation.json',self.generation);self.write(self.run/'evidence/summary.json',self.summary)
        self.write(self.run/'evidence/archive.json',{'status':'PASS','archive_sha256':trust.digest(self.archive.read_bytes()),'counts':trust.COUNTS})
        env=patch.dict(os.environ,{'RUNNER_TEMP':str(self.temp),'GITHUB_RUN_ID':'123','GITHUB_RUN_ATTEMPT':'1','GITHUB_REPOSITORY':'weilhuang/backend-interview-labs','GH_TOKEN':'synthetic'},clear=True);env.start();self.addCleanup(env.stop)
        self.window={'window_id':55,'pid':100,'x':321,'y':349,'width':638,'height':202,'border':0,'title_sha256':'c'*64}
        self.image=png();self.context=trust.context(self.root)
        self.request={**self.context,'schema':1,'stage':4,'action':trust.ACTION,'screenshot_sha256':trust.digest(self.image),
            'display_binding_sha256':trust.digest((self.root/'display-binding.properties').read_bytes()),'window_identity':self.window,
            'stage3_receipt_sha256':trust.digest((self.root/'stage-3/receipt.json').read_bytes())}
        self.approval={**copy.deepcopy(self.request),'visual_review':copy.deepcopy(trust.REVIEW)}
    def write(self,path,value):path.write_text(json.dumps(value))
    def stage(self):
        (self.root/'stage-4').mkdir();self.write(self.root/'stage-4/request.json',self.request);(self.root/'stage-4/before.png').write_bytes(self.image)

class SchemaTests(TrustFixture):
    def test_exact_sealed_source_request_and_fresh_review(self):self.assertEqual(trust.validate_control(self.approval,self.request),self.approval)
    def test_request_is_not_approval(self):
        with self.assertRaises(ValueError):trust.validate_control(self.request,self.request)
    def test_replay_wrong_binding_fields(self):
        for key,value in {'run_id':'124','run_attempt':'2','tested_sha':'b'*40,'source_tree':'c'*40,'archive_sha256':'b'*64,'screenshot_sha256':'d'*64,'display_binding_sha256':'e'*64,'stage3_receipt_sha256':'f'*64,'project_path_sha256':'f'*64,'project_relative_path':'academy-run-123-1/student','source_manifest_sha256':'a'*64,'stage':3,'action':'CHECK_EUA'}.items():
            with self.subTest(key=key),self.assertRaises(ValueError):trust.validate_control({**self.approval,key:value},self.request)
    def test_checkbox_title_scope_and_button_must_match(self):
        for key,value in [('parent_folder_trust_checked',True),('parent_folder_trust_checked',0),('parent_folder_trust_checked',None),('dialog','OTHER_PROJECT'),('scope','PARENT_FOLDER'),('button','PREVIEW_IN_SAFE_MODE')]:
            bad=copy.deepcopy(self.approval);bad['visual_review'][key]=value
            with self.subTest(key=key,value=value),self.assertRaises(ValueError):trust.validate_control(bad,self.request)
    def test_missing_and_extra_fields_rejected(self):
        for bad in [{k:v for k,v in self.approval.items() if k!='archive_sha256'},{**self.approval,'x':596},{**self.approval,'text':'Trust'}, {**self.approval,'visual_review':{**trust.REVIEW,'secret':{'command':'private'}}}]:
            with self.assertRaises(ValueError):trust.validate_control(bad,self.request)
    def test_boolean_numeric_types_rejected(self):
        for key in ('schema','stage'):
            bad={**self.request,key:True}
            with self.assertRaises(ValueError):trust.request_document(bad)
        for key in ('window_id','pid','x','y','width','height','border'):
            for value in (True,'1',1.0,None,{'private':'payload'}):
                bad=copy.deepcopy(self.request);bad['window_identity'][key]=value
                with self.subTest(key=key,value=value),self.assertRaises(ValueError):trust.request_document(bad)
    def test_nested_digest_or_giant_object_rejected(self):
        for value in ({'private':{'environment':'private'}},'a'*100000,False,None):
            with self.assertRaises(ValueError):trust.request_document({**self.request,'archive_sha256':value})
    def test_duplicate_keys_and_nonfinite_rejected(self):
        for raw in (b'{"schema":1,"schema":1}',b'{"schema":NaN}'):
            with self.assertRaises(ValueError):trust.json_read(raw)
    def test_invalid_window_geometry_and_changed_window_refused(self):
        for changes in ({'window_id':0},{'x':0,'width':10},{'height':0},{'width':2000},{'title_sha256':'private title'},{'raw_title':'secret'}):
            with self.assertRaises(ValueError):window.validate({**self.window,**changes})
        bad=copy.deepcopy(self.approval);bad['window_identity']['window_id']=56
        with self.assertRaises(ValueError):trust.validate_control(bad,self.request)

class ContextTests(TrustFixture):
    def test_different_104_payload_never_inherits_current_approval(self):
        self.write(self.run/'evidence/generation.json',{**self.generation,'tasks':104,'full_manifest_sha256':'d'*64})
        with self.assertRaises(ValueError):trust.context(self.root)
    def test_changed_archive_fails(self):
        self.archive.write_bytes(b'changed')
        with self.assertRaises(ValueError):trust.context(self.root)
    def test_wrong_source_ci_commit_fails(self):
        self.write(self.run/'evidence/source-ci.json',{**self.ci,'tested_sha':'d'*40})
        with self.assertRaises(ValueError):trust.context(self.root)
    def test_wrong_repository_fails(self):
        self.write(self.run/'evidence/summary.json',{**self.summary,'repository':'someone/else'})
        with self.assertRaises(ValueError):trust.context(self.root)
    def test_bool_counts_cannot_replace_integer_counts(self):
        self.write(self.run/'evidence/archive.json',{'status':'PASS','archive_sha256':trust.digest(self.archive.read_bytes()),'counts':{**trust.COUNTS,'courses':True}})
        with self.assertRaises(ValueError):trust.context(self.root)
    def test_validation_symlink_fails(self):
        (self.run/'validation').symlink_to(self.temp,target_is_directory=True)
        with self.assertRaises(ValueError):trust.context(self.root)
    def test_symlink_evidence_ancestor_fails(self):
        (self.run/'evidence').rename(self.run/'moved');(self.run/'evidence').symlink_to(self.run/'moved',target_is_directory=True)
        with self.assertRaises(OSError):trust.context(self.root)
    def test_archive_symlink_fails(self):
        self.archive.rename(self.run/'elsewhere');self.archive.symlink_to(self.run/'elsewhere')
        with self.assertRaises(OSError):trust.context(self.root)
    def test_other_run_path_cannot_be_used(self):
        other=self.temp/'academy-ui-124-1';other.mkdir()
        with self.assertRaises(ValueError):trust.context(other)
    def test_exact_cli_validation_target_required(self):
        idea=self.temp/'idea';command=[str(idea/'bin/idea'),'validateCourse',str(self.run/'validation'),'--archive',str(self.archive),'--tests','true','--links','true','--output-format','json','--output',str(self.run/'evidence/official-validation.json')]
        self.assertEqual(trust.context(self.root,command,idea),self.context)
        for at,value in [(0,'other'),(1,'createCourse'),(2,str(self.run/'student')),(4,str(self.run/'different.zip')),(6,'false')]:
            bad=command.copy();bad[at]=value
            with self.assertRaises(ValueError):trust.context(self.root,bad,idea)

class ReceiverTests(TrustFixture):
    def test_valid_record_written_once(self):
        self.stage()
        with patch.object(trust,'read_ui_deadline',return_value=100),patch.object(trust.time,'monotonic',return_value=50),patch.object(trust,'fetch_control',return_value=self.approval):trust.receive(self.root)
        self.assertEqual(trust.read_json(self.root/'stage-4/control.json'),self.approval)
        with patch.object(trust,'read_ui_deadline',return_value=100),self.assertRaises(ValueError):trust.receive(self.root)
    def test_expired_total_budget_does_not_fetch_or_write(self):
        self.stage()
        with patch.object(trust,'read_ui_deadline',return_value=100),patch.object(trust.time,'monotonic',return_value=100),patch.object(trust,'fetch_control') as fetch:
            with self.assertRaises(TimeoutError):trust.receive(self.root)
            fetch.assert_not_called()
        self.assertFalse((self.root/'stage-4/control.json').exists())
    def test_control_arriving_after_deadline_is_refused(self):
        self.stage()
        with patch.object(trust,'read_ui_deadline',return_value=100),patch.object(trust.time,'monotonic',side_effect=[98,99,100]),patch.object(trust,'fetch_control',return_value=self.approval):
            with self.assertRaises(ValueError):trust.receive(self.root)
        self.assertFalse((self.root/'stage-4/control.json').exists())
    def test_cancellation_propagates_without_control(self):
        self.stage()
        with patch.object(trust,'read_ui_deadline',return_value=100),patch.object(trust.time,'monotonic',return_value=50),patch.object(trust,'fetch_control',side_effect=InterruptedError):
            with self.assertRaises(InterruptedError):trust.receive(self.root)
        self.assertFalse((self.root/'stage-4/control.json').exists())

class EvidenceTests(TrustFixture):
    def test_request_only_is_not_performed_and_strips_png_metadata(self):
        self.stage();files=trust.collect(self.root,'123','1')
        self.assertEqual(set(files),{'project-trust-request.json','project-trust-before.png','project-trust-images.json'});self.assertNotIn(b'PRIVATE_METADATA',files['project-trust-before.png'])
        self.assertEqual(json.loads(files['project-trust-images.json'])['before_uploaded_sha256'],trust.digest(files['project-trust-before.png']))
    def test_current_receipt_after_image_collected(self):
        self.stage();(self.root/'stage-4/after.png').write_bytes(self.image)
        receipt={**self.approval,'after_sha256':trust.digest(self.image),'status':'UI_ACTION_PERFORMED_NOT_COURSE_ACCEPTANCE'};self.write(self.root/'stage-4/receipt.json',receipt)
        files=trust.collect(self.root,'123','1');self.assertEqual(len(files),5);self.assertNotIn(b'PRIVATE_METADATA',files['project-trust-after.png'])
    def test_other_attempt_and_stale_receipt_refused(self):
        self.stage()
        with self.assertRaises(ValueError):trust.collect(self.root,'123','2')
        self.write(self.root/'stage-4/receipt.json',{**self.approval,'run_id':'122','after_sha256':'a'*64,'status':'UI_ACTION_PERFORMED_NOT_COURSE_ACCEPTANCE'})
        with self.assertRaises(ValueError):trust.collect(self.root,'123','1')
    def test_changed_before_image_refused(self):
        self.stage();(self.root/'stage-4/before.png').write_bytes(b'private')
        with self.assertRaises(ValueError):trust.collect(self.root,'123','1')
    def test_raw_arbitrary_receipt_payload_rejected(self):
        self.stage();self.write(self.root/'stage-4/receipt.json',{**self.approval,'after_sha256':'a'*64,'status':'UI_ACTION_PERFORMED_NOT_COURSE_ACCEPTANCE','environment':{'TOKEN':'private'}})
        with self.assertRaises(ValueError):trust.collect(self.root,'123','1')
    def test_invalid_trust_receipt_does_not_expose_payload_or_erase_other_safe_logs(self):
        from collect_evidence import collect
        self.stage();self.write(self.root/'stage-4/receipt.json',{'environment':{'TOKEN':'PRIVATE_FIXTURE'}})
        (self.run/'evidence/validate.stderr.log').write_text('safe diagnostic\n')
        result=collect(self.run,self.temp/'artifact',ui_root=self.root,job_status='failure',cleanup_exit=0)
        self.assertTrue((self.temp/'artifact/validate.stderr.log').exists())
        self.assertFalse((self.temp/'artifact/project-trust-receipt.json').exists())
        for path in (self.temp/'artifact').iterdir():self.assertNotIn(b'PRIVATE_FIXTURE',path.read_bytes())
    def test_existing_collection_directory_cannot_reuse_old_evidence(self):
        from collect_evidence import collect
        out=self.temp/'artifact';out.mkdir();(out/'summary.json').write_bytes(b'OLD')
        with self.assertRaises(FileExistsError):collect(self.run,out,ui_root=self.root,job_status='failure',cleanup_exit=0)
        self.assertEqual((out/'summary.json').read_bytes(),b'OLD')

class WindowObservationTests(unittest.TestCase):
    class Function:
        def __init__(self,call):self.call=call
        def __call__(self,*args):return self.call(*args)
    def library(self,pid=100,title=b'fixed title',title_count=None,root_target=False):
        import ctypes as C
        lib=Mock();buffers=[];atoms={b'_NET_WM_PID':2,b'WM_NAME':3,b'CARDINAL':4,b'STRING':5}
        def setp(pointer,kind,value):C.cast(pointer,C.POINTER(kind))[0]=value
        def translate(conn,src,dest,x,y,px,py,child):
            setp(px,C.c_int,321 if src!=1 else x);setp(py,C.c_int,349 if src!=1 else y);setp(child,C.c_ulong,0 if root_target else 55);return 1
        def geometry(conn,win,root,x,y,width,height,border,depth):
            for ptr,kind,value in [(root,C.c_ulong,1),(x,C.c_int,321),(y,C.c_int,349),(width,C.c_uint,638),(height,C.c_uint,202),(border,C.c_uint,0),(depth,C.c_uint,24)]:setp(ptr,kind,value)
            return 1
        def prop(conn,win,atom,offset,size,delete,requested,actual,fmt,count,left,data):
            numeric=atom==2;buffer=(C.c_ulong*1)(pid) if numeric else C.create_string_buffer(title);buffers.append(buffer)
            for ptr,kind,value in [(actual,C.c_ulong,4 if numeric else 5),(fmt,C.c_int,32 if numeric else 8),(count,C.c_ulong,1 if numeric else (len(title) if title_count is None else title_count)),(left,C.c_ulong,0),(data,C.c_void_p,C.cast(buffer,C.c_void_p).value)]:setp(ptr,kind,value)
            return 0
        for name,call in {'XOpenDisplay':lambda *_:1,'XCloseDisplay':Mock(return_value=0),'XDefaultRootWindow':lambda *_:1,'XTranslateCoordinates':translate,'XGetGeometry':geometry,'XInternAtom':lambda conn,name,only:atoms[name],'XGetWindowProperty':prop,'XFree':lambda *_:0,'XSync':lambda *_:0,'XSetErrorHandler':lambda *_:0}.items():setattr(lib,name,self.Function(call))
        return lib
    def test_only_target_window_owned_pid_and_hashed_title_returned(self):
        lib=self.library(title=b'PRIVATE_SYNTHETIC_TITLE')
        with patch.dict(os.environ,{'DISPLAY':':99'}),patch.object(window.C,'CDLL',return_value=lib):value=window.observe(100)
        self.assertEqual(value['window_id'],55);self.assertEqual(value['pid'],100);self.assertEqual(value['title_sha256'],trust.digest(b'PRIVATE_SYNTHETIC_TITLE'));self.assertNotIn('PRIVATE',json.dumps(value));lib.XCloseDisplay.call.assert_called_once()
    def test_other_pid_is_rejected_and_connection_closes(self):
        lib=self.library(pid=101)
        with patch.dict(os.environ,{'DISPLAY':':99'}),patch.object(window.C,'CDLL',return_value=lib),self.assertRaises(ValueError):window.observe(100)
        lib.XCloseDisplay.call.assert_called_once()
    def test_no_window_at_button_fails_closed(self):
        lib=self.library(root_target=True)
        with patch.dict(os.environ,{'DISPLAY':':99'}),patch.object(window.C,'CDLL',return_value=lib),self.assertRaises(ValueError):window.observe(100)
    def test_oversized_title_refused_before_reading_arbitrary_memory(self):
        lib=self.library(title_count=100000)
        with patch.dict(os.environ,{'DISPLAY':':99'}),patch.object(window.C,'CDLL',return_value=lib),self.assertRaises(ValueError):window.observe(100)
    def test_remote_or_unknown_display_refused(self):
        for display in ('localhost:0','host:99',':12345','',':99.0'):
            with patch.dict(os.environ,{'DISPLAY':display}),self.assertRaises(ValueError):window.observe(100)
    def test_probe_is_time_and_output_bounded(self):
        result=Mock(stdout=b'X'*2049)
        with patch.object(trust.subprocess,'run',return_value=result) as run,self.assertRaises(ValueError):trust.window_probe(100,{})
        self.assertEqual(run.call_args.kwargs['timeout'],2)
    def test_probe_cancellation_propagates(self):
        with patch.object(trust.subprocess,'run',side_effect=InterruptedError),self.assertRaises(InterruptedError):trust.window_probe(100,{})

class ArtifactStagingTests(TrustFixture):
    def test_review_has_only_projected_json_and_sanitized_png_with_hash_mapping(self):
        self.stage();self.write(self.root/'stage-4/review-target.json',{'environment':{'TOKEN':'PRIVATE_FIXTURE'}})
        trust.stage_artifact(self.root,'review','123','1');out=self.root/'trust-review-artifact'
        self.assertEqual({p.name for p in out.iterdir()},{'project-trust-request.json','project-trust-before.png','project-trust-images.json','project-trust-review-target.json'})
        for path in out.iterdir():self.assertNotIn(b'PRIVATE_',path.read_bytes())
        mapping=trust.read_json(out/'project-trust-images.json');self.assertEqual(mapping['before_raw_sha256'],self.request['screenshot_sha256']);self.assertEqual(mapping['before_uploaded_sha256'],trust.digest((out/'project-trust-before.png').read_bytes()))
    def test_nested_raw_request_cannot_reach_review_artifact(self):
        self.stage();self.write(self.root/'stage-4/request.json',{**self.request,'environment':{'TOKEN':'PRIVATE_FIXTURE'}})
        with self.assertRaises(ValueError):trust.stage_artifact(self.root,'review','123','1')
        self.assertEqual(list((self.root/'trust-review-artifact').iterdir()),[])
    def test_nested_raw_receipt_cannot_reach_after_artifact(self):
        self.stage();self.write(self.root/'stage-4/receipt.json',{**self.approval,'environment':{'TOKEN':'PRIVATE_FIXTURE'}})
        with self.assertRaises(ValueError):trust.stage_artifact(self.root,'receipt','123','1')
        self.assertEqual(list((self.root/'trust-receipt-artifact').iterdir()),[])
    def test_old_artifact_never_overwritten_or_reused(self):
        self.stage();out=self.root/'trust-review-artifact';out.mkdir();(out/'project-trust-request.json').write_bytes(b'OLD')
        with self.assertRaises(FileExistsError):trust.stage_artifact(self.root,'review','123','1')
        self.assertEqual((out/'project-trust-request.json').read_bytes(),b'OLD')
    def test_review_after_prior_receipt_is_refused(self):
        self.stage();self.write(self.root/'stage-4/receipt.json',{})
        with self.assertRaises(ValueError):trust.stage_artifact(self.root,'review','123','1')
    def test_wrong_attempt_output_refused(self):
        self.stage()
        with self.assertRaises(ValueError):trust.stage_artifact(self.root,'review','123','2')
    def test_staging_cancellation_propagates(self):
        self.stage()
        with patch.object(trust,'collect',side_effect=InterruptedError),self.assertRaises(InterruptedError):trust.stage_artifact(self.root,'receipt','123','1')
    def test_workflow_failed_projection_never_sets_success_marker(self):
        import subprocess,yaml
        self.stage();self.write(self.root/'stage-4/receipt.json',{'environment':{'TOKEN':'PRIVATE_FIXTURE'}})
        repo=Path(trust.__file__).parents[2];workflow=yaml.safe_load((repo/'.github/workflows/academy-official.yml').read_text())
        for phase in ('review','receipt'):
            step=next(s for s in workflow['jobs']['package']['steps'] if s.get('id')=='trust_'+phase)
            output=self.temp/(phase+'-step-output')
            self.write(self.root/'stage-4/request.json',{**self.request,'private':'PRIVATE_FIXTURE'} if phase=='review' else self.request)
            env=dict(os.environ,PATH=str(Path(sys.executable).parent)+os.pathsep+os.defpath,UI_RUN=str(self.root),GITHUB_OUTPUT=str(output))
            result=subprocess.run(['bash','-e','-c',step['run']],cwd=repo,env=env,capture_output=True,timeout=10)
            self.assertEqual(result.returncode,1);self.assertFalse(output.exists())
            self.assertIn(b'ValueError: invalid project trust binding',result.stderr)
            self.assertEqual(list((self.root/('trust-'+phase+'-artifact')).iterdir()),[])

class CheckpointTests(TrustFixture):
    def setup_call(self,approval=True):
        proc=Mock();proc.poll.return_value=None;identity=Mock();identity.metadata={'ide':{'pid':100}};identity.binding=self.root/'display-binding.properties';owned=Mock()
        def screen(action,destination,*rest):
            destination.write_bytes(self.image)
            if action==trust.ACTION:
                self.assertEqual(rest[0],self.request['screenshot_sha256']);Path(rest[1]).write_text(trust.ACTION+'\n')
        original=trust.publish
        def publish(path,raw):
            original(path,raw)
            if path.name=='request.json' and approval:original(path.with_name('control.json'),trust.encode({**json.loads(raw),'visual_review':trust.REVIEW}))
        return proc,identity,owned,Mock(side_effect=screen),publish
    def call(self,proc,identity,owned,screen,publish,**patches):
        with patch.object(trust,'context',return_value=self.context),patch.object(trust,'window_probe',return_value=self.window),patch.object(trust,'publish',side_effect=publish),patch.object(trust.time,'monotonic',return_value=50):
            trust.checkpoint(self.root,proc,screen,identity,owned,100,[],self.temp,{})
    def test_fresh_bound_approval_performs_exact_one_normal_action(self):
        proc,identity,owned,screen,publish=self.setup_call();self.call(proc,identity,owned,screen,publish)
        self.assertEqual([call.args[0] for call in screen.call_args_list],['SNAPSHOT',trust.ACTION]);self.assertTrue((self.root/'stage-4/receipt.json').exists())
    def test_no_approval_never_clicks_and_cancellation_propagates(self):
        proc,identity,owned,screen,publish=self.setup_call(False);owned.scan.side_effect=InterruptedError
        with self.assertRaises(InterruptedError):self.call(proc,identity,owned,screen,publish)
        self.assertEqual([call.args[0] for call in screen.call_args_list],['SNAPSHOT']);self.assertFalse((self.root/'stage-4/receipt.json').exists())
    def test_window_change_before_click_refused(self):
        proc,identity,owned,screen,publish=self.setup_call()
        with patch.object(trust,'context',return_value=self.context),patch.object(trust,'window_probe',side_effect=[self.window,self.window,{**self.window,'window_id':56}]),patch.object(trust,'publish',side_effect=publish),patch.object(trust.time,'monotonic',return_value=50):
            with self.assertRaises(ValueError):trust.checkpoint(self.root,proc,screen,identity,owned,100,[],self.temp,{})
        self.assertEqual([call.args[0] for call in screen.call_args_list],['SNAPSHOT'])
    def test_old_or_expired_approval_cannot_click(self):
        proc,identity,owned,screen,publish=self.setup_call()
        with patch.object(trust.time,'monotonic',return_value=100):
            with self.assertRaises(ValueError):trust.checkpoint(self.root,proc,screen,identity,owned,100,[],self.temp,{})
        screen.assert_not_called()

class IntegrationStructureTests(unittest.TestCase):
    def test_eua_actions_and_deadline_unchanged(self):
        self.assertEqual(ui_control.ACTIONS,{1:'CHECK_EUA',2:'CONTINUE_EUA',3:'DECLINE_USAGE'});self.assertEqual(ui_control.UI_BUDGET_SECONDS,900)
    def test_robot_only_one_fixed_trust_button_with_rechecks(self):
        source=(Path(trust.__file__).parent/'probes/AgreementUi.java').read_text()
        self.assertIn('case "TRUST_VALIDATION_PROJECT": x=596; y=517;',source)
        self.assertEqual(source.count('verifyTrustWindow(args);'),2)
        self.assertEqual(source.count('robot.mousePress('),1);self.assertEqual(source.count('robot.mouseRelease('),1)
        self.assertIn('finalProbe.run();',source);self.assertLess(source.index('finalProbe.run();'),source.index('sha(image.read())'));self.assertLess(source.index('sha(image.read())'),source.index('click.run();'))
    def test_window_observation_never_enumerates_root_tree_or_exports_titles(self):
        source=Path(window.__file__).read_text();self.assertNotIn('XQueryTree',source);self.assertIn("'_NET_WM_PID'",source);self.assertNotIn('XSendEvent',source)
    def test_workflow_fourth_action_has_no_budget_extension(self):
        import yaml
        workflow=yaml.safe_load((Path(trust.__file__).parents[2]/'.github/workflows/academy-official.yml').read_text());job=workflow['jobs']['package'];steps=job['steps']
        self.assertIn('&& 85 || 30',job['timeout-minutes'])
        step=next(s for s in steps if 'project_trust.py receive' in s.get('run',''));self.assertEqual(step['timeout-minutes'],5)
        self.assertEqual(len([s for s in steps if 'ui_control.py --root' in s.get('run','')]),3)
        self.assertTrue(all('*' not in s['with']['path'] for s in steps if s.get('with',{}).get('name','').startswith(('academy-ui-stage-4-','academy-ui-project-trust-'))))
        for phase,prefix in [('review','academy-ui-stage-4-'),('receipt','academy-ui-project-trust-')]:
            upload=next(s for s in steps if s.get('with',{}).get('name','').startswith(prefix))
            self.assertIn("steps.trust_"+phase+".outputs.collected == 'true'",upload['if'])
            self.assertTrue(all('/trust-'+phase+'-artifact/' in p for p in upload['with']['path'].splitlines()));self.assertNotIn('/stage-4/',upload['with']['path'])

if __name__=='__main__':unittest.main()
