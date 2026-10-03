import copy
import json
import sys
from pathlib import Path
import unittest
from unittest.mock import patch, Mock
from contextlib import ExitStack
import os
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import profile_control as control
import plugin_agreement as plugin
from test_project_trust import TrustFixture
from test_modal_window import proof_fixture


class ProfileControlFixture(TrustFixture):
    def setUp(self):
        super().setUp()
        self.summary={'status':'PROSPECTIVE_VERIFIED','profile_name_sha256':'a'*64}
        self.private={'synthetic':'private profile candidate'}
        self.write(self.root/'profile-candidate.json',self.private)
        self.projection=patch('apparmor_profile.public_evidence',return_value=self.summary)
        self.projection.start();self.addCleanup(self.projection.stop)
        previous={**self.context,'schema':1,'stage':6,'action':plugin.ACTIONS[6],
                  'protocol':plugin.PROTOCOL,'terminal_stage':plugin.TERMINAL_STAGE,'legal_identity':plugin.LEGAL_ID,
                  'plugin_binary_sha256':plugin.PLUGIN_SHA,'screenshot_sha256':control.digest(self.image),'display_binding_sha256':'b'*64,
                  'window_identity':self.window,'preceding_receipt_sha256':'c'*64,
                  'comparison_mode':plugin.modal_pixels.MODE,'window_proof_sha256':control.digest(control.encode(proof_fixture(plugin.ACTIONS[6],self.window))),
                  'dialog_pixel_sha256':plugin.modal_pixels.pixel_hash(self.image,self.window)}
        (self.root/'stage-6').mkdir();(self.root/'stage-6/before.png').write_bytes(self.image);(self.root/'stage-6/modal-proof.json').write_bytes(control.encode(proof_fixture(plugin.ACTIONS[6],self.window)));self.write(self.root/'stage-6/request.json',previous)
        receipt={**previous,'visual_review':plugin.review(6),'after_sha256':'d'*64,'status':plugin.STATUS,'legal_rechecked':True}
        self.write(self.root/'stage-6/receipt.json',receipt)
        _,candidate_sha,_,public_sha=control.candidate(self.root)
        self.request={**self.context,'schema':1,'stage':7,'action':control.ACTIONS[7],'protocol':control.PROTOCOL,
                      'terminal_stage':11,'epoch':0,'screenshot_sha256':control.digest(self.image),
                      'display_binding_sha256':control.digest((self.root/'display-binding.properties').read_bytes()),
                      'windows':[self.window],'preceding_receipt_sha256':control.preceding(self.root,7),
                      'candidate_sha256':candidate_sha,'profile_evidence_sha256':public_sha,'active_context_sha256':None,'terminal_identity':None,'installed_profile_sha256':None}
        self.approval={**copy.deepcopy(self.request),'visual_review':control.review(7),
                       'target':{'window_id':self.window['window_id'],'point':[500,400]}}
    def staged(self):
        folder=self.root/'stage-7';folder.mkdir()
        self.write(folder/'request.json',self.request);(folder/'before.png').write_bytes(self.image)
        return folder


class ProfileControlTests(ProfileControlFixture):
    def test_real_owner_exit_during_fetch_cannot_publish_control(self):
        from test_ui_session import real_budget_owner
        self.staged()
        with real_budget_owner(self.root) as (_,_,exit_unreaped):
            def fetch(*args):exit_unreaped();return self.approval
            with patch.object(control,'fetch_control',side_effect=fetch),self.assertRaises(ValueError):control.receive(self.root,7)
            self.assertFalse((self.root/'stage-7/control.json').exists())

    def test_current_bounded_point_requires_full_control(self):
        self.assertEqual(control.validate_control(self.approval,self.request),self.approval)
        with self.assertRaises(ValueError):control.validate_control(self.request,self.request)

    def test_wrong_run_source_epoch_hash_and_protocol_fail(self):
        changes={'run_id':'124','run_attempt':'2','source_tree':'c'*40,'archive_sha256':'d'*64,
                 'epoch':1,'candidate_sha256':'e'*64,'screenshot_sha256':'f'*64,'terminal_stage':6,'protocol':plugin.PROTOCOL}
        for key,value in changes.items():
            with self.subTest(key=key),self.assertRaises(ValueError):control.validate_control({**self.approval,key:value},self.request)

    def test_coordinates_are_strict_and_bound_to_reviewed_window(self):
        for target in ({'window_id':999,'point':[500,400]},{'window_id':55,'point':[-1,400]},
                       {'window_id':55,'point':[True,400]},{'window_id':55,'point':[500,900]},
                       {'window_id':55,'point':[500,'400']},{'window_id':55,'point':[500,400],'text':'private'}):
            with self.subTest(target=target),self.assertRaises(ValueError):control.validate_control({**self.approval,'target':target},self.request)

    def test_auth_dialog_sandbox_choice_or_other_scope_fail(self):
        for key,value in [('authentication_dialog',True),('disable_sandbox',True),('button','DISABLE_SANDBOX'),('dialog','AUTHENTICATION')]:
            bad=copy.deepcopy(self.approval);bad['visual_review'][key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):control.validate_control(bad,self.request)

    def test_nested_and_boolean_type_confusion_fail(self):
        for key in ('schema','stage','epoch','terminal_stage'):
            with self.assertRaises(ValueError):control.request_document({**self.request,key:True})
        for key in ('screenshot_sha256','candidate_sha256','profile_evidence_sha256'):
            with self.assertRaises(ValueError):control.request_document({**self.request,key:{'environment':{'X':'PRIVATE'}}})

    def test_observation_has_no_target_or_input_authority(self):
        request={**self.request,'stage':10,'action':control.ACTIONS[10],'epoch':1,'active_context_sha256':'1'*64}
        approved={**request,'visual_review':control.review(10)}
        self.assertEqual(control.validate_control(approved,request),approved)
        with self.assertRaises(ValueError):control.validate_control({**approved,'target':self.approval['target']},request)

    def test_restart_install_receipt_cannot_claim_success_or_after_image(self):
        request={**self.request,'stage':8,'action':control.ACTIONS[8]}
        approved={**request,'visual_review':control.review(8),'target':self.approval['target']}
        receipt={**approved,'status':'INSTALL_CLICK_DISPATCHED_OUTCOME_UNVERIFIED','after_sha256':None}
        control.receipt_document(receipt,request)
        for changes in ({'status':'INSTALLED_VERIFIED'},{'after_sha256':'a'*64},{'status':'PASS'}):
            with self.assertRaises(ValueError):control.receipt_document({**receipt,**changes},request)

    def test_public_artifact_contains_only_projected_fixed_files(self):
        self.staged();out=control.collect(self.root,7,'123','1')
        self.assertEqual(set(out),{'profile-stage-7-request.json','profile-stage-7-before.png',
                                  'profile-stage-7-profile-summary.json','profile-stage-7-images.json'})
        self.assertNotIn(b'private profile candidate',b''.join(out.values()))

    def test_malformed_receipt_cannot_enter_artifact(self):
        folder=self.staged();self.write(folder/'receipt.json',{'environment':{'X':'SYNTHETIC_PRIVATE'}})
        with self.assertRaises(ValueError):control.collect(self.root,7,'123','1')

    def test_duplicate_and_huge_request_keys_fail(self):
        with self.assertRaises(ValueError):control.json_read(b'{"schema":1,"schema":1}')
        with self.assertRaises(ValueError):control.request_document({**self.request,'windows':[self.window]*1000})

    def test_symlink_candidate_and_old_artifact_output_fail(self):
        self.staged();control.stage_artifact(self.root,7,'review','123','1')
        with self.assertRaises(FileExistsError):control.stage_artifact(self.root,7,'review','123','1')
        (self.root/'profile-candidate.json').rename(self.root/'elsewhere');(self.root/'profile-candidate.json').symlink_to(self.root/'elsewhere')
        with self.assertRaises(OSError):control.collect(self.root,7,'123','1')

    def test_cancel_latch_blocks_receiving_control(self):
        self.staged();self.write(self.root/'cancelled.json',{'schema':1,'cancelled':True})
        with patch.object(control,'fetch_control') as fetch,self.assertRaises(InterruptedError):control.receive(self.root,7)
        fetch.assert_not_called();self.assertFalse((self.root/'stage-7/control.json').exists())

    def test_context_has_fixed_scalars_and_exact_active_mode(self):
        value={**self.context,'schema':1,'epoch':1,'pid':100,'start_time':'123','status':'CONTEXT_VERIFIED',
               'interface':'APPARMOR_CURRENT','mode':'unconfined','profile_name_sha256':'a'*64,'context_sha256':'b'*64}
        control.context_document(value)
        for key,other in [('pid',True),('epoch',False),('interface','ARBITRARY_FILE'),('mode','complain'),('context_sha256',{'private':'data'})]:
            with self.assertRaises(ValueError):control.context_document({**value,key:other})


class TerminalControlTests(ProfileControlFixture):
    def terminal_request(self):
        return {**self.request,'stage':9,'action':control.ACTIONS[9],
                'terminal_identity':{'pid':100,'ppid':99,'pgrp':100,'session':100,'uid':1000,'start_time':'12','executable_sha256':'a'*64},
                'installed_profile_sha256':'b'*64}

    def test_completion_accepts_only_enter_and_no_target(self):
        expected=self.terminal_request();approved={**expected,'visual_review':control.review(9)}
        control.validate_control(approved,expected)
        for extra in ({'target':self.approval['target']},{'text':'secret'},{'key':'SPACE'}):
            with self.subTest(extra=extra),self.assertRaises(ValueError):control.validate_control({**approved,**extra},expected)
        for field,value in [('password_prompt',True),('authentication_dialog',True),('key','PASSWORD'),('installation_completed',False)]:
            with self.subTest(field=field),self.assertRaises(ValueError):control.validate_control({**approved,'visual_review':{**approved['visual_review'],field:value}},expected)

    def test_terminal_replay_identity_and_installed_hash_fail(self):
        expected=self.terminal_request();approved={**expected,'visual_review':control.review(9)}
        for field,value in [('terminal_identity',{**expected['terminal_identity'],'start_time':'13'}),('installed_profile_sha256','c'*64),('terminal_stage',10),('protocol','SCOPED_PROFILE_PREPARATION_AND_FRESH_VALIDATION_V1')]:
            with self.subTest(field=field),self.assertRaises(ValueError):control.validate_control({**approved,field:value},expected)
        for value in (True,'100',{'environment':'PRIVATE'},None):
            with self.subTest(value=value),self.assertRaises(ValueError):control.terminal_document({**expected['terminal_identity'],'pid':value})

    def test_terminal_receipt_records_dispatch_not_restart(self):
        expected=self.terminal_request();receipt={**expected,'visual_review':control.review(9),'status':'TERMINAL_ENTER_DISPATCHED_RESTART_UNVERIFIED','after_sha256':None}
        control.receipt_document(receipt,expected)
        for changes in ({'status':'INSTALLED_VERIFIED'},{'status':'RESTART_VERIFIED'},{'after_sha256':'a'*64}):
            with self.assertRaises(ValueError):control.receipt_document({**receipt,**changes},expected)

    def checkpoint(self,change=None):
        terminal=Mock(pid=101,key=(101,'12'));proc=Mock(pid=100);proc.poll.return_value=None
        family=Mock();family.verify_terminal_helpers.return_value=change!='live-helper'
        family.members={terminal.key:{'meta':{'pid':101,'ppid':100,'pgrp':101,'session':101,'uid':os.getuid(),'start_time':'12'},'fd':9}}
        identity=Mock();identity.binding=self.root/'display-binding.properties'
        self.write(self.root/'stage-8-control-fixture.json',{'install':'synthetic'})
        (self.root/'stage-8').mkdir();self.write(self.root/'stage-8/control.json',{'install':'synthetic'})
        terminal_window={**self.window,'pid':101,'window_id':56}
        private={'parser':{'expected_helpers':{'TERMINAL':{'sha256':'a'*64}}}}
        installed=control.encode({**self.summary,'status':'INSTALLED_VERIFIED','exact_name_count':1})
        original=control.publish;actions=[];snapshots=[]
        def publish(path,raw):
            original(path,raw)
            if path.name=='request.json':
                request=control.json_read(raw)
                original(path.with_name('control.json'),control.encode({**request,'visual_review':control.review(9)}))
                if change=='cancel':original(self.root/'cancelled.json',b'{}')
        def screen(action,destination,*args,**kwargs):
            if action=='SNAPSHOT':snapshots.append(action);destination.write_bytes(self.image)
            else:
                actions.append(action)
                if change=='during-key':raise InterruptedError('synthetic')
                args[1].write_text(action+'\n')
        with ExitStack() as stack:
            for patcher in [patch.object(control,'candidate',return_value=(private,'a'*64,self.summary,'b'*64)),
                    patch.object(control,'preceding',return_value='c'*64),patch.object(control,'terminal_current'),
                    patch.object(control,'installed_bytes',side_effect=ValueError('synthetic') if change=='bad-install' else None,return_value=installed),
                    patch.object(control,'observe',side_effect=ValueError('synthetic focus') if change=='wrong-focus' else None,return_value=[self.window,terminal_window]),
                    patch.object(control,'publish',side_effect=publish),patch.object(control.time,'monotonic',return_value=10)]:stack.enter_context(patcher)
            try:control.checkpoint(self.root,9,proc,screen,identity,family,100,{},terminal=terminal)
            except (ValueError,InterruptedError):return family,actions,snapshots,False
        return family,actions,snapshots,True

    def test_checkpoint_binds_fresh_installed_bytes_then_single_enter(self):
        family,actions,shots,passed=self.checkpoint()
        self.assertTrue(passed);self.assertEqual(actions,[control.ACTIONS[9]]);self.assertEqual(shots,['SNAPSHOT'])
        family.terminal_acknowledged.assert_called_once()
        receipt=control.json_read((self.root/'stage-9/receipt.json').read_bytes())
        self.assertEqual(receipt['status'],'TERMINAL_ENTER_DISPATCHED_RESTART_UNVERIFIED')

    def test_terminal_artifact_is_exact_and_rejects_boolean_installed_count(self):
        family,actions,shots,passed=self.checkpoint();self.assertTrue(passed)
        with patch.object(control,'candidate',return_value=(self.private,'a'*64,self.summary,'b'*64)),patch.object(control,'preceding',return_value='c'*64):
            files=control.collect(self.root,9,'123','1')
            self.assertEqual(set(files),{'profile-stage-9-request.json','profile-stage-9-before.png','profile-stage-9-profile-summary.json',
                'profile-stage-9-installed-profile.json','profile-stage-9-receipt.json','profile-stage-9-images.json'})
            folder=self.root/'stage-9';request=control.json_read((folder/'request.json').read_bytes())
            raw=control.encode({**self.summary,'status':'INSTALLED_VERIFIED','exact_name_count':True})
            (folder/'installed-profile.json').write_bytes(raw)
            request['installed_profile_sha256']=control.digest(raw);self.write(folder/'request.json',request)
            with self.assertRaises(ValueError):control.collect(self.root,9,'123','1')

    def test_live_helper_prevents_image_and_key(self):
        f,actions,shots,passed=self.checkpoint('live-helper');self.assertFalse(passed)
        self.assertEqual(actions+shots,[]);f.terminal_acknowledged.assert_not_called()

    def test_unverified_install_prevents_image_and_key(self):
        f,actions,shots,passed=self.checkpoint('bad-install');self.assertFalse(passed)
        self.assertEqual(actions+shots,[]);f.terminal_acknowledged.assert_not_called()

    def test_wrong_focus_prevents_image_and_key(self):
        f,actions,shots,passed=self.checkpoint('wrong-focus');self.assertFalse(passed)
        self.assertEqual(actions+shots,[]);f.terminal_acknowledged.assert_not_called()

    def test_cancel_after_approval_never_sends_enter(self):
        f,actions,shots,passed=self.checkpoint('cancel');self.assertFalse(passed)
        self.assertEqual(actions,[]);f.terminal_acknowledged.assert_not_called()
        self.assertFalse((self.root/'stage-9/receipt.json').exists())

    def test_cancel_during_key_never_certifies_restart(self):
        f,actions,shots,passed=self.checkpoint('during-key');self.assertFalse(passed)
        f.terminal_acknowledged.assert_not_called();self.assertFalse((self.root/'stage-9/receipt.json').exists())


class TerminalFocusTests(unittest.TestCase):
    def test_focus_ancestry_accepts_only_current_terminal(self):
        control.window.focused_window(60,55,lambda pid:{60:59,59:55}[pid])
        control.window.focused_window(55,55,lambda _:self.fail('unneeded query'))
    def test_focus_cycle_unrelated_root_and_depth_limit_fail(self):
        for focus,parent in [(60,lambda _:60),(60,lambda _:1),(60,lambda n:n+1),(0,lambda _:55)]:
            with self.assertRaises(ValueError):control.window.focused_window(focus,55,parent)


if __name__=='__main__':unittest.main()
