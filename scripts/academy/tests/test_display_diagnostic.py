"""Pure PNG/receipt fixtures and mocks; no Java, real display or UI action."""
import copy,hashlib,json,os,struct,sys,tempfile,unittest,zlib
from pathlib import Path
from unittest.mock import Mock,patch,MagicMock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import display_diagnostic as diag
import ui_control
import ui_session
from collect_evidence import collect as collect_all

def png(metadata=b'PRIVATE_METADATA',width=1280,height=900):
    def chunk(kind,data):return struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data)&0xffffffff)
    return b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',width,height,8,2,0,0,0))+chunk(b'tEXt',metadata)+chunk(b'IDAT',zlib.compress(b'\0'*(height*(1+width*3))))+chunk(b'IEND',b'')
class DisplayTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)/'academy-ui-123-1';self.root.mkdir();(self.root/'stage-3').mkdir()
        self.receipt={'run_id':'123','run_attempt':'1','stage':3,'action':'DECLINE_USAGE','status':'UI_ACTION_PERFORMED_NOT_ACCEPTANCE'}
        (self.root/'stage-3/receipt.json').write_text(json.dumps(self.receipt));(self.root/'display-binding.properties').write_text('fixed synthetic identity')
        self.identity=Mock();self.identity.binding=self.root/'display-binding.properties';self.proc=Mock();self.proc.poll.return_value=None
        self.env=patch.dict(os.environ,{'GITHUB_RUN_ID':'123','GITHUB_RUN_ATTEMPT':'1'});self.env.start();self.addCleanup(self.env.stop)
    def screen(self,*args):
        self.assertEqual(args,('SNAPSHOT',self.root/diag.PNG_NAME));(self.root/diag.PNG_NAME).write_bytes(png())
    def capture(self):
        with patch.object(diag.time,'monotonic',return_value=100):return diag.capture(self.root,self.proc,self.screen,self.identity,101)
    def test_only_snapshot_action_and_bound_metadata_stripped(self):
        self.assertEqual(self.capture(),'CAPTURED_NOT_ACCEPTANCE');self.assertEqual(self.identity.verify.call_count,2)
        files=diag.collect(self.root,'123','1');self.assertEqual(set(files),{diag.PNG_NAME,diag.REPORT_NAME})
        self.assertNotIn(b'PRIVATE_METADATA',files[diag.PNG_NAME]);v=json.loads(files[diag.REPORT_NAME]);self.assertEqual(v['action'],'SNAPSHOT_ONLY');self.assertEqual(v['uploaded_screenshot_sha256'],hashlib.sha256(files[diag.PNG_NAME]).hexdigest())
    def test_exited_ide_cannot_take_image(self):
        self.proc.poll.return_value=0;screen=Mock()
        self.assertEqual(diag.capture(self.root,self.proc,screen,self.identity,99999999),'UNAVAILABLE_IDE_EXITED');screen.assert_not_called();self.identity.verify.assert_not_called()
        self.assertEqual(set(diag.collect(self.root,'123','1')),{diag.REPORT_NAME})
    def test_expired_ui_budget_cannot_take_image(self):
        screen=Mock()
        with patch.object(diag.time,'monotonic',return_value=100):self.assertEqual(diag.capture(self.root,self.proc,screen,self.identity,100),'UNAVAILABLE_UI_DEADLINE')
        screen.assert_not_called()
    def test_identity_change_prevents_capture(self):
        self.identity.verify.side_effect=RuntimeError('PRIVATE identity');screen=Mock()
        self.assertEqual(diag.capture(self.root,self.proc,screen,self.identity,99999999),'UNAVAILABLE_IDENTITY_OR_CAPTURE');screen.assert_not_called();self.assertNotIn('PRIVATE',(self.root/diag.REPORT_NAME).read_text())
    def test_missing_receipt_keeps_typed_unavailable(self):
        (self.root/'stage-3/receipt.json').unlink();screen=Mock();self.assertEqual(diag.capture(self.root,self.proc,screen,self.identity,99999999),'UNAVAILABLE_RECEIPT');screen.assert_not_called()
        self.assertEqual(set(diag.collect(self.root,'123','1')),{diag.REPORT_NAME})
    def test_interruption_propagates_through_capture_and_optional_caller(self):
        screen=Mock(side_effect=InterruptedError('cancelled'))
        with self.assertRaises(InterruptedError):diag.capture(self.root,self.proc,screen,self.identity,99999999)
        self.assertFalse((self.root/diag.REPORT_NAME).exists())
        with patch.object(ui_session,'capture_display_diagnostic',side_effect=InterruptedError('cancelled')):
            with self.assertRaises(InterruptedError):ui_session.optional_display_diagnostic(self.root,self.proc,screen,self.identity,99999999)
    def test_cancelled_post_ui_capture_runs_existing_session_cleanup(self):
        jar=MagicMock();jar.__enter__.return_value=jar;jar.getinfo.return_value.file_size=7;jar.read.return_value=b'fixture'
        proc=Mock();proc.pid=100;proc.poll.return_value=None;proc.wait.return_value=-15
        owned=Mock();owned.members={100:({'pid':100},9)};owned.register_root.return_value={'pid':100,'start_time':'0','uid':0,'session':100,'pgrp':100}
        identity=Mock();identity.metadata={'fixture':True};identity.handles={};identity.binding=self.root/'display-binding.properties'
        root=Path(self.tmp.name)/'session-cancel';root.mkdir();clock=[0];original=ui_session.put
        def now():clock[0]+=1;return clock[0]
        def put(path,value):
            original(path,value)
            if path.name=='request.json':original(path.with_name('control.json'),value)
        def screen_command(args,**kwargs):Path(args[6]).write_bytes(b'PNG_FIXTURE')
        with patch.object(ui_session,'trust_context'),patch.object(ui_session.zipfile,'ZipFile',return_value=jar),patch.object(ui_session,'EUA_SHA256',hashlib.sha256(b'fixture').hexdigest()),patch.object(ui_control,'EUA_SHA256',hashlib.sha256(b'fixture').hexdigest()),patch.object(ui_session,'Owned',return_value=owned),patch.object(ui_session,'DisplayIdentity',return_value=identity),patch.object(ui_session.subprocess,'Popen',return_value=proc),patch.object(ui_session.subprocess,'run',side_effect=screen_command),patch.object(ui_session.signal,'signal'),patch.object(ui_session.time,'monotonic',side_effect=now),patch.object(ui_session.time,'sleep'),patch.object(ui_session,'put',side_effect=put),patch.object(ui_session,'capture_display_diagnostic',side_effect=InterruptedError('cancelled')):
            with self.assertRaises(InterruptedError):ui_session.display_session(root,root,['fixture'])
        owned.stop.assert_called_once();identity.close.assert_called_once();proc.wait.assert_called_once()
    def test_report_is_complete_before_its_name_becomes_visible(self):
        original=diag.os.link;seen=[]
        def observe(source,destination,**kwargs):
            with self.assertRaises(FileNotFoundError):os.stat(destination,dir_fd=kwargs['dst_dir_fd'],follow_symlinks=False)
            fd=os.open(source,os.O_RDONLY,dir_fd=kwargs['src_dir_fd'])
            try:raw=os.read(fd,4096)
            finally:os.close(fd)
            value=json.loads(raw);self.assertEqual(value['status'],'CAPTURED_NOT_ACCEPTANCE');seen.append(value)
            return original(source,destination,**kwargs)
        with patch.object(diag.os,'link',side_effect=observe):self.capture()
        self.assertEqual(len(seen),1);self.assertEqual(json.loads((self.root/diag.REPORT_NAME).read_text()),seen[0]);self.assertEqual(list(self.root.glob('.pending-*')),[])
    def test_atomic_publication_never_replaces_existing_output(self):
        p=self.root/'existing.json';p.write_bytes(b'OLD')
        with self.assertRaises(FileExistsError):diag.publish(p,b'NEW')
        self.assertEqual(p.read_bytes(),b'OLD');self.assertEqual(list(self.root.glob('.pending-*')),[])
    def test_optional_observation_is_outside_all_approval_step_caps(self):
        import yaml
        workflow=yaml.load((Path(__file__).resolve().parents[3]/'.github/workflows/academy-official.yml').read_text(),Loader=yaml.BaseLoader)
        steps=workflow['jobs']['package']['steps'];approval=[s for s in steps if 'ui_control.py' in s.get('run','')]
        self.assertEqual(len(approval),3)
        self.assertTrue(all(s['timeout-minutes']=='5' and 'display_diagnostic.py' not in s['run'] for s in approval))
        optional=next(s for s in steps if 'display_diagnostic.py' in s.get('run',''))
        self.assertEqual(optional['continue-on-error'],'true');self.assertEqual(optional['timeout-minutes'],'1')
        self.assertGreater(steps.index(optional),steps.index(approval[-1]))
        # A late t=280s approval has no new30/45s wait inside its t=300s cap.
        self.assertNotIn('wait_collect',approval[-1]['run'])
    def test_failed_optional_collector_cannot_upload_old_output(self):
        import yaml,subprocess
        workflow=yaml.load((Path(__file__).resolve().parents[3]/'.github/workflows/academy-official.yml').read_text(),Loader=yaml.BaseLoader)
        steps=workflow['jobs']['package']['steps'];step=next(s for s in steps if s.get('id')=='ui_diagnostic')
        upload=next(s for s in steps if s.get('with',{}).get('name','').startswith('academy-ui-diagnostic-'))
        self.assertEqual(upload['continue-on-error'],'true');self.assertIn("steps.ui_diagnostic.outputs.collected == 'true'",upload['if'])
        self.assertEqual(upload['id'],'ui_diagnostic_upload')
        self.assertEqual(len([s for s in steps if 'continue-on-error' in s]),2)
        self.assertEqual(step['run'].strip().splitlines(),['python scripts/academy/display_diagnostic.py --root "$UI_RUN" --output "$UI_RUN/diagnostic-artifact" --run-id "$GITHUB_RUN_ID" --run-attempt "$GITHUB_RUN_ATTEMPT"', 'printf \'collected=true\\n\' >> "$GITHUB_OUTPUT"'])
        self.assertEqual(upload['with']['path'].splitlines(),['${{ env.UI_RUN }}/diagnostic-artifact/post-ui-diagnostic.json','${{ env.UI_RUN }}/diagnostic-artifact/post-ui-diagnostic.png'])
        root=Path(self.tmp.name)/'shell';(root/'scripts/academy').mkdir(parents=True)
        (root/'scripts/academy/display_diagnostic.py').write_text('raise SystemExit(1)\n')
        old=self.root/'diagnostic-artifact';old.mkdir();(old/diag.REPORT_NAME).write_text('OLD')
        env=dict(os.environ,UI_RUN=str(self.root),GITHUB_RUN_ID='123',GITHUB_RUN_ATTEMPT='1',GITHUB_OUTPUT=str(root/'output'))
        result=subprocess.run(['bash','-e','-c',step['run']],cwd=root,env=env,capture_output=True,timeout=5)
        self.assertNotEqual(result.returncode,0);self.assertFalse((root/'output').exists());self.assertEqual((old/diag.REPORT_NAME).read_text(),'OLD')
    def test_capture_timeout_is_diagnostic_only(self):
        screen=Mock(side_effect=TimeoutError('PRIVATE command'))
        self.assertEqual(diag.capture(self.root,self.proc,screen,self.identity,99999999),'UNAVAILABLE_IDENTITY_OR_CAPTURE');self.assertNotIn('PRIVATE',(self.root/diag.REPORT_NAME).read_text())
    def test_wrong_run_or_attempt_rejected(self):
        self.capture()
        for run,attempt in [('124','1'),('123','2'),(True,'1'),('123',1)]:
            with self.subTest(run=run,attempt=attempt),self.assertRaises(ValueError):diag.collect(self.root,run,attempt)
    def test_changed_receipt_or_display_binding_rejected(self):
        self.capture()
        for relative in ['stage-3/receipt.json','display-binding.properties']:
            p=self.root/relative;old=p.read_bytes();p.write_bytes(old+b' ')
            with self.assertRaises(ValueError):diag.collect(self.root,'123','1')
            p.write_bytes(old)
    def test_changed_or_symlinked_screenshot_rejected(self):
        self.capture();p=self.root/diag.PNG_NAME;p.write_bytes(png(b'changed'))
        with self.assertRaises(ValueError):diag.collect(self.root,'123','1')
        p.unlink();foreign=Path(self.tmp.name)/'foreign.png';foreign.write_bytes(png());p.symlink_to(foreign)
        with self.assertRaises(OSError):diag.collect(self.root,'123','1')
    def test_symlinked_ancestor_rejected(self):
        self.capture();link=Path(self.tmp.name)/'alias';link.symlink_to(self.root,target_is_directory=True)
        with self.assertRaises(OSError):diag.collect(link,'123','1')
    def test_png_dimensions_bounds_structure_and_crc(self):
        valid=png()
        for bad in [png(width=1,height=1),valid[:-1],valid+b'x',valid[:-6]+b'badcrc',b'x'*(diag.MAX_PNG+1)]:
            with self.subTest(length=len(bad)),self.assertRaises(ValueError):diag.clean_png(bad)
    def test_nested_private_values_and_boolean_numeric_types_rejected(self):
        self.capture();v=json.loads((self.root/diag.REPORT_NAME).read_text())
        for key,value in [('schema_version',True),('after_stage',True),('delay_seconds',True),('run_id',{}),('status',{'command':'PRIVATE'}),('at_utc',[]),('screenshot_sha256',{'environment':'PRIVATE'})]:
            changed={**v,key:value}
            with self.subTest(key=key),self.assertRaises(ValueError):diag.project_report(changed)
        v['unknown']={'command':'PRIVATE'};self.assertNotIn('PRIVATE',json.dumps(diag.project_report(v)))
        for raw in [b'{"schema_version":1,"schema_version":1}',b'{"x":NaN}']:
            with self.assertRaises(ValueError):diag.json_read(raw)
    def test_wait_is_bounded_by_existing_ui_deadline(self):
        clock=[0.0]
        with patch.object(ui_control,'read_ui_deadline',return_value=2),patch.object(diag.time,'monotonic',side_effect=lambda:clock[0]),patch.object(diag.time,'sleep',side_effect=lambda seconds:clock.__setitem__(0,clock[0]+seconds)):
            diag.wait_collect(self.root,self.root/'diagnostic-artifact','123','1')
        self.assertLessEqual(clock[0],2.2);v=json.loads((self.root/'diagnostic-artifact'/diag.REPORT_NAME).read_text());self.assertEqual(v['status'],'UNAVAILABLE');self.assertFalse((self.root/'diagnostic-artifact'/diag.PNG_NAME).exists())
    def test_wait_stops_for_terminal_supervisor(self):
        (self.root/'result.json').write_text('{}')
        with patch.object(ui_control,'read_ui_deadline',return_value=99999999),patch.object(diag.time,'sleep') as sleep:diag.wait_collect(self.root,self.root/'diagnostic-artifact','123','1')
        sleep.assert_not_called()
    def test_existing_output_is_never_reused(self):
        target=self.root/'diagnostic-artifact';target.mkdir();(target/'old').write_text('PRIVATE')
        with self.assertRaises(FileExistsError):diag.wait_collect(self.root,target,'123','1')
        self.assertEqual((target/'old').read_text(),'PRIVATE')
    def test_collector_binds_image_to_current_summary_run(self):
        self.capture();run=Path(self.tmp.name)/'run';(run/'evidence').mkdir(parents=True);(run/'evidence/summary.json').write_text(json.dumps({'status':'FAIL','run_id':'124','run_attempt':'1'}))
        output=Path(self.tmp.name)/'artifact';collect_all(run,output,ui_root=self.root)
        self.assertFalse((output/diag.PNG_NAME).exists());self.assertIn('INVALID_OR_UNAVAILABLE',(output/'collection.json').read_text())
    def test_existing_loop_delays_once_without_new_action_or_budget(self):
        source=(Path(__file__).resolve().parents[1]/'ui_session.py').read_text()
        self.assertIn('diagnostic_due=time.monotonic()+30;diagnostic_done=False',source)
        self.assertIn('not diagnostic_done and time.monotonic()>=diagnostic_due',source)
        self.assertIn('owned=Owned(started+2700)',source)
        self.assertNotIn('ACCEPT_TRUST',source)
if __name__=='__main__':unittest.main()
