"""Synthetic plugin-only approvals; no agreement, AI, browser or GUI action occurs."""
import copy,json,subprocess,sys,unittest
from pathlib import Path
from unittest.mock import Mock,patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import plugin_agreement as plugin
import project_trust as trust
from test_project_trust import TrustFixture

class PluginFixture(TrustFixture):
    def setUp(self):
        super().setUp();super().stage()
        (self.root/'stage-4/after.png').write_bytes(self.image)
        self.write(self.root/'stage-4/receipt.json',{**self.approval,'after_sha256':trust.digest(self.image),'status':plugin.STATUS})
        self.window={'window_id':56,'pid':100,'x':380,'y':335,'width':520,'height':235,'border':0,'title_sha256':'e'*64}
        self.request=self.make_request(5);self.approval={**copy.deepcopy(self.request),'visual_review':plugin.review(5)}
    def make_request(self,stage):
        return {**self.context,'schema':1,'stage':stage,'action':plugin.ACTIONS[stage],'protocol':plugin.PROTOCOL,'terminal_stage':plugin.TERMINAL_STAGE,
            'legal_identity':dict(plugin.LEGAL_ID),'plugin_binary_sha256':plugin.PLUGIN_SHA,
            'preceding_receipt_sha256':plugin.preceding(self.root,stage,self.context),
            'screenshot_sha256':trust.digest(self.image),'display_binding_sha256':trust.digest((self.root/'display-binding.properties').read_bytes()),'window_identity':self.window}
    def stage(self,stage=5,complete=False):
        request=self.make_request(stage);folder=self.root/f'stage-{stage}';folder.mkdir()
        self.write(folder/'request.json',request);(folder/'before.png').write_bytes(self.image)
        if complete:
            (folder/'after.png').write_bytes(self.image)
            self.write(folder/'receipt.json',{**request,'visual_review':plugin.review(stage),'after_sha256':trust.digest(self.image),'status':plugin.STATUS,'legal_rechecked':True})
        return request

class BindingTests(PluginFixture):
    def test_two_stages_have_separate_fresh_checkbox_states(self):
        plugin.validate_control(self.approval,self.request);self.stage(5,True)
        second=self.make_request(6);plugin.validate_control({**second,'visual_review':plugin.review(6)},second)
        self.assertFalse(plugin.review(5)['plugin_checked']);self.assertTrue(plugin.review(6)['plugin_checked'])
        self.assertFalse(plugin.review(5)['ai_training_checked']);self.assertFalse(plugin.review(6)['ai_training_checked'])
    def test_no_request_is_approval(self):
        with self.assertRaises(ValueError):plugin.validate_control(self.request,self.request)
    def test_wrong_run_source_image_previous_receipt_or_stop_protocol_rejected(self):
        for key,value in {'run_id':'124','run_attempt':'2','tested_sha':'b'*40,'source_tree':'c'*40,'archive_sha256':'c'*64,'source_manifest_sha256':'c'*64,
            'project_relative_path':'academy-run-123-1/other','project_path_sha256':'c'*64,'preceding_receipt_sha256':'c'*64,'screenshot_sha256':'c'*64,
            'display_binding_sha256':'c'*64,'protocol':'R11_POST_TRUST_CANCEL','terminal_stage':4,'plugin_binary_sha256':'c'*64,'stage':6,'action':'INSTALL_PROFILE'}.items():
            with self.subTest(key=key),self.assertRaises(ValueError):plugin.validate_control({**self.approval,key:value},self.request)
    def test_ai_selection_wrong_dialog_scope_or_disabled_agree_rejected(self):
        for stage in (5,6):
            expected=copy.deepcopy(self.request);expected.update(stage=stage,action=plugin.ACTIONS[stage])
            for key,value in [('ai_training_checked',True),('ai_training_checked',0),('plugin_checked',stage!=6),('agree_enabled',stage!=6),('dialog','OTHER'),('scope','AI_FEATURES'),('button','ENABLE_BROWSER')]:
                approval={**expected,'visual_review':{**plugin.review(stage),key:value}}
                with self.subTest(stage=stage,key=key),self.assertRaises(ValueError):plugin.validate_control(approval,expected)
    def test_changed_legal_version_hash_or_nested_payload_rejected(self):
        for value in ({**plugin.LEGAL_ID,'privacy_version':'3.3'},{**plugin.LEGAL_ID,'documents_sha256':'d'*64},{'environment':{'secret':'PRIVATE'}},None):
            with self.assertRaises(ValueError):plugin.request_document({**self.request,'legal_identity':value})
        for key in ('stage','schema','terminal_stage'):
            with self.assertRaises(ValueError):plugin.request_document({**self.request,key:True})
        with self.assertRaises(ValueError):plugin.request_document({**self.request,'command':{'PRIVATE':'X'}})
    def test_changed_or_missing_preceding_receipt_rejected(self):
        self.write(self.root/'stage-4/receipt.json',{'status':'PASS'})
        with self.assertRaises(ValueError):plugin.preceding(self.root,5,self.context)
    def test_stage6_cannot_skip_checkbox_receipt_or_relabel_other_stage(self):
        with self.assertRaises(FileNotFoundError):plugin.preceding(self.root,6,self.context)
        self.stage(5,True);value=trust.read_json(self.root/'stage-5/request.json');value['stage']=6;self.write(self.root/'stage-5/request.json',value)
        with self.assertRaises(ValueError):plugin.preceding(self.root,6,self.context)
    def test_exact_target_enum_rejects_coordinates_or_security_actions(self):
        for action in ((448,443),'INSTALL_PROFILE','DISABLE_SANDBOX','AI_AGREEMENT',None):
            with self.assertRaises(ValueError):plugin.window.target(action)
        self.assertEqual(plugin.window.target(plugin.ACTIONS[5]),(448,403));self.assertEqual(plugin.window.target(plugin.ACTIONS[6]),(765,539))
    def test_wrong_window_pid_or_hash_replay_rejected(self):
        for key,value in [('pid',101),('window_id',57),('title_sha256','a'*64),('width',True)]:
            bad=copy.deepcopy(self.approval);bad['window_identity'][key]=value
            with self.assertRaises(ValueError):plugin.validate_control(bad,self.request)

class LegalTests(unittest.TestCase):
    def test_pins_bind_two_reviewed_official_pdf_bodies_and_versions(self):
        items=plugin.pins();self.assertEqual(len(items),2)
        self.assertEqual({(i['document'],i['version'],i['format']) for i in items},{('plugin','1.3','pdf'),('privacy','3.2','pdf')})
    def mocked_fetch(self,changed=False,redirect=False):
        body=b'synthetic legal body';item={'url':'https://www.jetbrains.com/legal/fixture','format':'pdf','bytes':len(body),'sha256':trust.digest(body)}
        response=Mock();response.__enter__=Mock(return_value=response);response.__exit__=Mock(return_value=False)
        response.status=200;response.geturl.return_value=item['url'] if not redirect else 'https://other.invalid/'
        response.read.return_value=body+(b'x' if changed else b'')
        opener=Mock();opener.open.return_value=response
        return item,opener
    def test_exact_body_verified_without_transmitting_credentials(self):
        item,opener=self.mocked_fetch()
        with patch.object(plugin,'pins',return_value=[item]),patch.object(plugin.urllib.request,'build_opener',return_value=opener),patch.object(plugin.time,'monotonic',return_value=50):self.assertEqual(plugin.fetch_legal(100),plugin.LEGAL_ID)
        request=opener.open.call_args.args[0];self.assertEqual(dict(request.header_items()),{'Accept-encoding':'identity'})
    def test_changed_body_redirect_and_expiry_fail_closed(self):
        for changed,redirect in [(True,False),(False,True)]:
            item,opener=self.mocked_fetch(changed,redirect)
            with patch.object(plugin,'pins',return_value=[item]),patch.object(plugin.urllib.request,'build_opener',return_value=opener),patch.object(plugin.time,'monotonic',return_value=50),self.assertRaises(ValueError):plugin.fetch_legal(100)
        with patch.object(plugin.time,'monotonic',return_value=100),patch.object(plugin.subprocess,'run') as run,self.assertRaises(ValueError):plugin.verify_legal(100)
        run.assert_not_called()
    def test_entire_download_has_hard_subprocess_budget_and_clean_environment(self):
        with patch.dict(plugin.os.environ,{'GH_TOKEN':'PRIVATE_FIXTURE'},clear=True),patch.object(plugin.time,'monotonic',return_value=90),patch.object(plugin.subprocess,'run',return_value=Mock(stdout=trust.encode(plugin.LEGAL_ID))) as run:
            plugin.verify_legal(100)
        self.assertEqual(run.call_args.kwargs['timeout'],10);self.assertEqual(set(run.call_args.kwargs['env']),{'PATH','LANG'})
    def test_network_timeout_or_cancellation_cannot_become_acceptance(self):
        for error in (InterruptedError(),subprocess.TimeoutExpired('fixture',2)):
            with patch.object(plugin.time,'monotonic',return_value=90),patch.object(plugin.subprocess,'run',side_effect=error),self.assertRaises(type(error)):plugin.verify_legal(100)
    def test_changed_local_pin_file_rejected(self):
        with patch.object(plugin,'read_regular',return_value=b'{"secret":{}}'),self.assertRaises(ValueError):plugin.pins()

class ReceiverTests(PluginFixture):
    def test_current_control_only_once(self):
        self.stage()
        with patch.object(plugin,'read_ui_deadline',return_value=100),patch.object(plugin.time,'monotonic',return_value=50),patch.object(plugin,'fetch_control',return_value=self.approval):plugin.receive(self.root,5)
        with patch.object(plugin,'read_ui_deadline',return_value=100),self.assertRaises(ValueError):plugin.receive(self.root,5)
    def test_late_control_cancel_and_expired_budget_do_not_write(self):
        self.stage()
        for error in (InterruptedError(),ValueError('stale')):
            with patch.object(plugin,'read_ui_deadline',return_value=100),patch.object(plugin.time,'monotonic',return_value=50),patch.object(plugin,'fetch_control',side_effect=error),self.assertRaises(type(error)):plugin.receive(self.root,5)
        with patch.object(plugin,'read_ui_deadline',return_value=100),patch.object(plugin.time,'monotonic',side_effect=[98,99,100]),patch.object(plugin,'fetch_control',return_value=self.approval),self.assertRaises(ValueError):plugin.receive(self.root,5)
        self.assertFalse((self.root/'stage-5/control.json').exists())

class ArtifactTests(PluginFixture):
    def test_fresh_projection_only_and_sanitized_image_hash_mapping(self):
        self.stage();plugin.stage_artifact(self.root,5,'review','123','1');out=self.root/'plugin-5-review-artifact'
        self.assertEqual(len(list(out.iterdir())),4)
        for path in out.iterdir():self.assertNotIn(b'PRIVATE_',path.read_bytes())
        self.assertEqual(trust.read_json(out/'plugin-stage-5-images.json')['before_raw_sha256'],self.request['screenshot_sha256'])
    def test_receipt_requires_real_stage_and_cannot_reuse_output(self):
        self.stage()
        with self.assertRaises(ValueError):plugin.stage_artifact(self.root,5,'receipt','123','1')
        with self.assertRaises(FileExistsError):plugin.stage_artifact(self.root,5,'receipt','123','1')
    def test_nested_arbitrary_payload_rejected_before_any_output(self):
        self.stage(5,True);path=self.root/'stage-5/receipt.json';value=trust.read_json(path);value['environment']={'TOKEN':'PRIVATE_FIXTURE'};self.write(path,value)
        with self.assertRaises(ValueError):plugin.stage_artifact(self.root,5,'receipt','123','1')
        self.assertEqual(list((self.root/'plugin-5-receipt-artifact').iterdir()),[])
    def test_malformed_collection_preserves_safe_logs_without_private_payload(self):
        from collect_evidence import collect
        self.stage();self.write(self.root/'stage-5/request.json',{'environment':{'TOKEN':'PRIVATE_FIXTURE'}})
        (self.run/'evidence/validate.stderr.log').write_text('safe\n');out=self.temp/'artifact'
        collect(self.run,out,ui_root=self.root,job_status='failure',cleanup_exit=0)
        self.assertTrue((out/'validate.stderr.log').exists())
        for path in out.iterdir():self.assertNotIn(b'PRIVATE_FIXTURE',path.read_bytes())
    def test_symlink_before_image_and_wrong_attempt_rejected(self):
        self.stage();before=self.root/'stage-5/before.png';before.unlink();before.symlink_to(self.root/'stage-4/before.png')
        with self.assertRaises(OSError):plugin.collect(self.root,5,'123','1')
        with self.assertRaises(ValueError):plugin.collect(self.root,5,'123','2')
    def test_workflow_projection_failure_never_sets_upload_marker(self):
        import os,yaml
        self.stage();self.write(self.root/'stage-5/request.json',{'environment':{'TOKEN':'PRIVATE_FIXTURE'}})
        repo=Path(plugin.__file__).parents[2];doc=yaml.safe_load((repo/'.github/workflows/academy-official.yml').read_text())
        step=next(s for s in doc['jobs']['package']['steps'] if s.get('id')=='plugin_5_review');out=self.temp/'output'
        result=subprocess.run(['bash','-e','-c',step['run']],cwd=repo,env=dict(os.environ,PATH=str(Path(sys.executable).parent)+os.pathsep+os.defpath,UI_RUN=str(self.root),GITHUB_OUTPUT=str(out)),capture_output=True,timeout=10)
        self.assertEqual(result.returncode,1);self.assertFalse(out.exists());self.assertEqual(list((self.root/'plugin-5-review-artifact').iterdir()),[])

class CheckpointTests(PluginFixture):
    def call(self,mode='success'):
        proc=Mock();proc.poll.return_value=None;identity=Mock();identity.metadata={'ide':{'pid':100}};identity.binding=self.root/'display-binding.properties';owned=Mock();actions=[]
        def screen(action,dest,*args):
            actions.append(action);dest.write_bytes(self.image)
            if action in plugin.ACTIONS.values():Path(args[1]).write_text(action+'\n')
        original=plugin.publish
        def publish(path,raw):
            original(path,raw)
            if path.name=='request.json':
                value={**json.loads(raw),'visual_review':plugin.review(5)}
                if mode=='ai':value['visual_review']['ai_training_checked']=True
                original(path.with_name('control.json'),trust.encode(value))
        with patch.object(plugin,'verify_plugin',return_value=plugin.PLUGIN_SHA),patch.object(plugin,'verify_legal',side_effect=InterruptedError if mode=='cancel' else lambda *_:dict(plugin.LEGAL_ID)),patch.object(plugin,'window_probe',return_value=self.window),patch.object(plugin,'publish',side_effect=publish),patch.object(plugin.time,'monotonic',return_value=50):
            try:plugin.checkpoint(self.root,5,proc,screen,identity,owned,100,[],self.temp,{})
            except BaseException:
                self.assertNotIn(plugin.ACTIONS[5],actions);raise
        return actions
    def test_approved_current_image_performs_exact_one_base_checkbox_click(self):
        with patch.object(trust,'context',return_value=self.context):actions=self.call()
        self.assertEqual(actions,['SNAPSHOT',plugin.ACTIONS[5]])
        self.assertEqual(trust.read_json(self.root/'stage-5/receipt.json')['status'],plugin.STATUS)
    def test_ai_approval_or_cancellation_never_clicks(self):
        with patch.object(trust,'context',return_value=self.context),self.assertRaises(ValueError):self.call('ai')
    def test_legal_cancellation_propagates_before_creating_request(self):
        with patch.object(trust,'context',return_value=self.context),self.assertRaises(InterruptedError):self.call('cancel')
        self.assertFalse((self.root/'stage-5').exists())


class FinalProbeTests(PluginFixture):
    def prepare(self):
        self.stage();self.write(self.root/'stage-5/control.json',self.approval);self.write(self.root/'stage-5/window-identity.json',self.window)
    def test_current_window_and_deadline_rechecked_after_metadata_probe(self):
        self.prepare()
        with patch.object(plugin,'read_ui_deadline',return_value=100),patch.object(plugin.time,'monotonic',side_effect=[98,100]),patch.object(plugin.window,'observe',return_value=self.window),self.assertRaises(ValueError):plugin.verify_window(self.root,self.root/'stage-5/window-identity.json')
    def test_wrong_path_or_window_never_authorizes_click(self):
        self.prepare()
        with self.assertRaises(ValueError):plugin.verify_window(self.root,self.root/'stage-4/window-identity.json')
        with patch.object(plugin,'read_ui_deadline',return_value=100),patch.object(plugin.time,'monotonic',return_value=50),patch.object(plugin.window,'observe',return_value={**self.window,'pid':101}),self.assertRaises(ValueError):plugin.verify_window(self.root,self.root/'stage-5/window-identity.json')
    def test_metadata_probe_cancellation_propagates(self):
        self.prepare()
        with patch.object(plugin,'read_ui_deadline',return_value=100),patch.object(plugin.time,'monotonic',return_value=50),patch.object(plugin.window,'observe',side_effect=InterruptedError),self.assertRaises(InterruptedError):plugin.verify_window(self.root,self.root/'stage-5/window-identity.json')

class WorkflowBoundaryTests(unittest.TestCase):
    def test_exact_review_and_receipt_outputs_require_fresh_projection(self):
        import yaml
        repo=Path(plugin.__file__).parents[2];steps=yaml.safe_load((repo/'.github/workflows/academy-official.yml').read_text())['jobs']['package']['steps']
        for stage in (5,6):
            for phase in ('review','receipt'):
                projection=next(s for s in steps if s.get('id')==f'plugin_{stage}_{phase}')
                self.assertNotIn('continue-on-error',projection)
                self.assertTrue(projection['run'].index('stage-artifact')<projection['run'].index('collected=true'))
                upload=next(s for s in steps if s.get('uses','').startswith('actions/upload-artifact@') and f'plugin-{stage}-{phase}-artifact' in s.get('with',{}).get('path',''))
                self.assertIn(f"steps.plugin_{stage}_{phase}.outputs.collected == 'true'",upload['if'])
                self.assertNotIn('*',upload['with']['path']);self.assertEqual(upload['with']['retention-days'],1)
    def test_source_and_timing_and_security_surfaces_are_narrow(self):
        repo=Path(plugin.__file__).parents[2];session=(repo/'scripts/academy/restart_session.py').read_text();helper=(repo/'scripts/academy/probes/AgreementUi.java').read_text()
        self.assertIn('for stage in (5,6):',session);self.assertIn('plugin.checkpoint(root,stage,current,screen,identity,family,ui_deadline,command,idea,helper_env,runner=family.run)',session)
        self.assertIn('case "INSTALL_SCOPED_APPARMOR_PROFILE"',helper);self.assertNotIn('case "DISABLE_SANDBOX"',helper)
        self.assertIn('if (bound)',helper);self.assertIn('finalTrustClick',helper)

if __name__=='__main__':unittest.main()
