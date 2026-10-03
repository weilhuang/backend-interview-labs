"""Composition and public diagnostic boundaries for only the two plugin actions."""
import copy,json,sys,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import plugin_agreement as plugin
import profile_control
from test_plugin_agreement import PluginFixture
from test_modal_window import proof_fixture
from test_modal_pixels import sample_png

class ModalControls(PluginFixture):
    def staged_control(self):
        self.stage();(self.root/'stage-5/control.json').write_bytes(plugin.encode(self.approval))
    def failure(self,**updates):
        value={'schema':1,'action':plugin.ACTIONS[5],'phase':'INITIAL_ONE','reason':'MODAL_PIXELS_CHANGED','dispatch_state':'NO_INPUT_DISPATCHED',
            'approved_full_sha256':self.request['screenshot_sha256'],'approved_dialog_sha256':self.request['dialog_pixel_sha256'],
            'approved_proof_sha256':self.request['window_proof_sha256'],'current_full_sha256':'a'*64,'current_dialog_sha256':'b'*64,
            'current_proof_sha256':self.request['window_proof_sha256'],'private_frame_status':'RETAINED_PRIVATE_ONLY',**updates}
        (self.root/'stage-5/comparison-failure.json').write_bytes(plugin.encode(value));return value
    def test_control_and_receipt_stay_inside_4096_reader_contract(self):
        self.stage(5,True);self.stage(6,True)
        for stage in (5,6):
            folder=self.root/f'stage-{stage}';request=plugin.request_document(plugin.json_read((folder/'request.json').read_bytes()))
            self.assertLessEqual(len(plugin.encode({**request,'visual_review':plugin.review(stage)})),4096)
            self.assertLessEqual(len((folder/'receipt.json').read_bytes()),4096)
            plugin.read_modal(folder,request)
        self.assertEqual(profile_control.preceding(self.root,7),plugin.digest((self.root/'stage-6/receipt.json').read_bytes()))
    def test_all_new_small_bindings_reject_old_or_changed_approval(self):
        for key,value in [('comparison_mode','WHOLE_DISPLAY'),('window_proof_sha256','c'*64),('dialog_pixel_sha256','c'*64)]:
            with self.assertRaises(ValueError):plugin.validate_control({**self.approval,key:value},self.request)
        for key in ('complete_dialog_visible','dialog_unobscured','all_decision_controls_inside'):
            for value in (False,1,None):
                with self.assertRaises(ValueError):plugin.validate_control({**self.approval,'visual_review':{**self.approval['visual_review'],key:value}},self.request)
    def test_sidecar_path_symlink_hash_and_full_image_are_bound(self):
        self.stage();folder=self.root/'stage-5';path=folder/'modal-proof.json';original=path.read_bytes()
        path.write_bytes(original+b' ')
        with self.assertRaises(ValueError):plugin.read_modal(folder,self.request)
        path.unlink();path.symlink_to(folder/'request.json')
        with self.assertRaises(OSError):plugin.read_modal(folder,self.request)
        path.unlink();path.write_bytes(original);(folder/'before.png').write_bytes(sample_png({(0,0):(1,2,3)}))
        with self.assertRaises(ValueError):plugin.read_modal(folder,self.request)
    def test_smaller_crop_cannot_substitute_for_window(self):
        self.stage();changed=copy.deepcopy(self.request);changed['window_identity']['width']-=1
        with self.assertRaises(ValueError):plugin.read_modal(self.root/'stage-5',changed)
    def test_failure_image_never_public_even_when_window_and_hash_are_valid(self):
        self.staged_control();self.failure();(self.root/'stage-5/comparison-failure-private.png').write_bytes(b'PRIVATE_PROMPT_FIXTURE')
        files=plugin.collect(self.root,5,'123','1')
        receipt=plugin.json_read(files['plugin-stage-5-comparison-failure.json'])
        self.assertEqual(receipt['failure_image_public'],'NOT_CLEARED');self.assertEqual(receipt['dispatch_state'],'NO_INPUT_DISPATCHED')
        self.assertNotIn('plugin-stage-5-comparison-failure.png',files)
        for raw in files.values():self.assertNotIn(b'PRIVATE_PROMPT_FIXTURE',raw)
    def test_failure_private_frame_is_never_opened(self):
        self.staged_control();self.failure();(self.root/'stage-5/comparison-failure-private.png').symlink_to('/unavailable-private-file')
        self.assertIn('plugin-stage-5-comparison-failure.json',plugin.collect(self.root,5,'123','1'))
    def test_unknown_current_values_remain_null_and_do_not_claim_pixels(self):
        self.staged_control();self.failure(reason='WINDOW_PROOF_UNAVAILABLE',phase='FINAL_PROBE',current_full_sha256=None,current_dialog_sha256=None,current_proof_sha256=None,private_frame_status='UNAVAILABLE')
        result=plugin.collect_failure(self.root/'stage-5',self.request)
        self.assertIsNone(result['current_full_sha256']);self.assertIsNone(result['current_proof_sha256'])
    def test_malformed_optional_evidence_preserves_safe_request(self):
        self.staged_control()
        for changes in ({'reason':{'environment':'PRIVATE_TOKEN'}},{'current_full_sha256':False},{'phase':'POST_PRESS'},{'schema':True},{'command':'PRIVATE_COMMAND'}):
            self.failure(**changes);files=plugin.collect(self.root,5,'123','1')
            self.assertIn('plugin-stage-5-request.json',files)
            self.assertEqual(plugin.json_read(files['plugin-stage-5-comparison-failure.json'])['status'],'INVALID_OPTIONAL_DIAGNOSTIC')
            for raw in files.values():self.assertNotIn(b'PRIVATE_',raw)
    def test_duplicate_keys_and_old_control_fail_receipt(self):
        self.staged_control();value=self.failure();path=self.root/'stage-5/comparison-failure.json'
        path.write_bytes(plugin.encode(value)[:-2]+b',"schema":1}\n')
        self.assertEqual(plugin.json_read(plugin.collect(self.root,5,'123','1')['plugin-stage-5-comparison-failure.json'])['status'],'INVALID_OPTIONAL_DIAGNOSTIC')
        self.failure();self.write(self.root/'stage-5/control.json',{**self.approval,'run_attempt':'2'})
        with self.assertRaises(ValueError):plugin.collect_failure(self.root/'stage-5',self.request)
    def test_post_press_failure_cannot_claim_no_input(self):
        self.staged_control();self.failure(reason='OWNERSHIP_OR_ACTION_UNAVAILABLE',phase='POST_PRESS',dispatch_state='DISPATCH_STARTED',current_full_sha256=None,current_dialog_sha256=None,current_proof_sha256=None,private_frame_status='UNAVAILABLE')
        self.assertEqual(plugin.collect_failure(self.root/'stage-5',self.request)['dispatch_state'],'DISPATCH_STARTED')
    def test_short_companion_line_binds_strict_sidecar_and_pixels(self):
        self.staged_control();self.write(self.root/'stage-5/window-identity.json',self.window)
        with patch.object(plugin,'read_ui_budget',return_value=({'monotonic_deadline':100},100)),patch.object(plugin,'read_ui_deadline',return_value=100),patch.object(plugin.time,'monotonic',return_value=50),patch.object(plugin.modal_window,'observe',return_value=proof_fixture(plugin.ACTIONS[5],self.window)):
            line=plugin.verify_window(self.root,self.root/'stage-5/window-identity.json')
        self.assertEqual(line,'MODAL1 380 335 520 235 '+self.request['dialog_pixel_sha256']+' '+self.request['screenshot_sha256']+' '+self.request['window_proof_sha256'])
    def test_live_budget_owner_dying_inside_blocking_proof_cannot_authorize(self):
        from test_ui_session import real_budget_owner
        self.staged_control();self.write(self.root/'stage-5/window-identity.json',self.window)
        with real_budget_owner(self.root) as (_,_,exit_unreaped):
            def observe(*_):exit_unreaped();return proof_fixture(plugin.ACTIONS[5],self.window)
            with patch.object(plugin.modal_window,'observe',side_effect=observe),self.assertRaises(ValueError):
                plugin.verify_window(self.root,self.root/'stage-5/window-identity.json')

    def test_all_three_actual_java_sites_use_modal_only_for_plugin(self):
        source=(Path(plugin.__file__).with_name('probes')/'AgreementUi.java').read_text()
        self.assertIn('if (plugin) pluginInitialComparisons',source)
        self.assertEqual(source.count('state.compare(image.read())'),3)
        self.assertEqual(source.count('if (!sha(capture(robot,bounds)).equals(args[2]))'),2)
        self.assertIn('else if (bound)',source);self.assertIn('finalTrustClick',source)
        self.assertLess(source.index('modal.dispatch="DISPATCH_STARTED"'),source.index('robot.mousePress'))
    def test_no_public_upload_path_for_changed_frame(self):
        workflow=(Path(plugin.__file__).parents[2]/'.github/workflows/academy-official.yml').read_text()
        self.assertNotIn('comparison-failure-private.png',workflow)
        self.assertNotIn('comparison-failure.png',workflow)

if __name__=='__main__':unittest.main()
