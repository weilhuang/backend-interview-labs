"""Mocked lifecycle composition; no IDE, GUI, profile install, or OS policy action."""
from contextlib import ExitStack
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import Mock, MagicMock, patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import restart_session as session
import ui_session as ui
import ui_control
import post_trust_diagnostic as diagnostic
import apparmor_profile as profile
from test_project_trust import TrustFixture


class RestartHarness(TrustFixture):
    def run_composition(self,fail_at=None):
        # A separate root avoids the trust fixture's already-created stage 3.
        root=self.temp/'composition';root.mkdir()
        os.environ['HOME']=str(self.temp/'home')
        (root/'display-binding.properties').write_bytes(b'fixture')
        (root/'wrapper.json').write_text('{}')
        def meta(pid):return {'pid':pid,'ppid':1,'pgrp':pid,'session':pid,'start_time':'0','uid':os.getuid()}
        children=[]
        for pid in (101,102,103):
            child=Mock();child.pid=pid;child.key=(pid,'0');child.poll.return_value=None;child.returncode=0;children.append(child)
        first,restarted,fresh=children
        family=Mock();family.members={c.key:{'meta':{**meta(c.pid),'state':'R'},'fd':9,'terminal':False} for c in children}
        family.spawn.side_effect=[first,fresh];family.replacement.return_value=restarted
        family.terminal_child.return_value=Mock(pid=104);family.verify_terminal_helpers.return_value=True
        family.restart_provenance.return_value='OBSERVED_RESTARTER_EXEC'
        identity=Mock();identity.handles={};identity.binding=root/'display-binding.properties';identity.metadata={'ide':meta(101)}
        def establish(folder,observed,*args):
            identity.metadata={'ide':observed};identity.binding=folder/'display-binding.properties'
            if not identity.binding.exists():identity.binding.write_bytes(b'fixture')
        identity.establish.side_effect=establish
        jar=MagicMock();jar.__enter__.return_value=jar;jar.getinfo.return_value.file_size=7;jar.read.return_value=b'fixture'
        clock=[0]
        def now():clock[0]+=1;return clock[0]
        original=ui.put
        def put(path,value):
            if fail_at=='deadline-write' and path.name=='ui-deadline.json':raise OSError('synthetic')
            original(path,value)
            if path.name=='request.json':original(path.with_name('control.json'),value)
        def helper(args,**kwargs):
            action=args[5];Path(args[6]).write_bytes(b'SYNTHETIC_PNG')
            if action!='SNAPSHOT':Path(args[8]).write_text(action+'\n')
            return subprocess.CompletedProcess(args,0)
        family.run.side_effect=helper
        observer=Mock();observer.done=True
        if fail_at=='observer':observer.done=False;observer.tick.side_effect=InterruptedError('synthetic')
        acknowledged=[False]
        def replacement():
            self.assertTrue(acknowledged[0], 'replacement waited before terminal acknowledgement')
            return restarted
        family.replacement.side_effect=replacement
        def profile_checkpoint(_root,stage,*args,**kwargs):
            if fail_at==stage:raise InterruptedError('synthetic')
            if stage==9:acknowledged[0]=True
            if stage==11:fresh.poll.return_value=0
        context={**self.context}
        active={'status':'CONTEXT_VERIFIED','interface':'APPARMOR_CURRENT','mode':'unconfined',
                'profile_name_sha256':'a'*64,'context_sha256':'b'*64}
        with ExitStack() as stack:
            values=[patch.object(session,'Family',return_value=family),patch.object(ui,'read_outer_deadline',return_value=2700),
                patch.object(ui,'process_info',side_effect=meta),patch.object(ui,'DisplayIdentity',return_value=identity),
                patch.object(session.zipfile,'ZipFile',return_value=jar),patch.object(session,'EUA_SHA256',hashlib.sha256(b'fixture').hexdigest()),
                patch.object(ui_control,'EUA_SHA256',hashlib.sha256(b'fixture').hexdigest()),patch.object(session.signal,'signal'),
                patch.object(session.time,'monotonic',side_effect=now),patch.object(session.time,'sleep'),patch.object(ui,'put',side_effect=put),
                patch.object(session.trust,'context',return_value=context),patch.object(diagnostic,'context',return_value=context),patch.object(session.trust,'checkpoint'),
                patch.object(session.plugin,'checkpoint',new=self._diagnostic_checkpoint) if fail_at=='real-plugin-failure' else patch.object(session.plugin,'checkpoint'),patch.object(ui,'PostTrustObserver',return_value=observer),
                patch.object(ui,'optional_display_diagnostic',side_effect=InterruptedError('synthetic') if fail_at=='capture' else None),
                patch.object(session.os,'readlink',return_value='/sdk/idea/bin/idea'),patch.object(profile,'prepare',return_value={'parser':{'route':'TERMINAL_SUDO','expected_helpers':{}}}),
                patch.object(profile,'verify_installed',return_value={'status':'INSTALLED_VERIFIED','exact_name_count':1}),
                patch.object(profile,'verify_context',return_value=active),patch.object(session.control,'checkpoint',side_effect=profile_checkpoint),
                patch.object(session,'fresh_validation_layout',return_value={'fixture':True})]
            for item in values:stack.enter_context(item)
            if fail_at=='profile':stack.enter_context(patch.object(profile,'prepare',side_effect=profile.ProfileError('PROFILE_COLLISION')))
            if fail_at=='context':stack.enter_context(patch.object(profile,'verify_context',side_effect=profile.ProfileError('CONTEXT_MISMATCH')))
            if fail_at=='root-direct':stack.enter_context(patch.object(profile,'prepare',return_value={'parser':{'route':'ROOT_DIRECT','expected_helpers':{}}}))
            if fail_at=='adopted':family.restart_provenance.return_value='CLOSED_FAMILY_ADOPTED_EXEC'
            if fail_at=='live-helper':family.verify_terminal_helpers.return_value=False
            if fail_at=='cleanup':family.close_phase.side_effect=RuntimeError('synthetic')
            result=session.display_session(root,root,['fixture'])
        receipt=json.loads((root/session.RESULT).read_text())
        return result,receipt,family,identity,children


class CompositionTests(RestartHarness):
    def test_distinct_fresh_validation_follows_verified_cleanup(self):
        code,receipt,family,identity,children=self.run_composition()
        self.assertEqual(code,0,receipt);self.assertEqual(receipt['status'],'FRESH_VALIDATION_EXITED_NOT_ACCEPTANCE')
        self.assertEqual(family.spawn.call_count,2);family.close_phase.assert_called_once();family.begin_validation.assert_called_once()
        self.assertEqual(receipt['course_acceptance'],'NOT_RUN');self.assertTrue(receipt['validation_cleanup'])

    def test_adopted_restart_provenance_is_truthful(self):
        code,r,family,_,_=self.run_composition('adopted')
        self.assertEqual(code,0);self.assertEqual(r['restart_provenance'],'CLOSED_FAMILY_ADOPTED_EXEC')

    def test_root_direct_route_stops_before_install(self):
        code,r,family,_,_=self.run_composition('root-direct')
        self.assertEqual(code,1);family.configure_restart_images.assert_not_called();family.begin_validation.assert_not_called()

    def test_surviving_helper_exhausts_bounded_completion_without_p2(self):
        code,r,family,_,_=self.run_composition('live-helper')
        self.assertEqual(code,1);self.assertFalse(r['phase2_started']);family.replacement.assert_not_called();family.begin_validation.assert_not_called()

    def test_cancelled_optional_capture_cleans_and_never_launches_p2(self):
        code,r,family,identity,_=self.run_composition('capture')
        self.assertEqual(code,1);self.assertTrue(r['cancelled']);self.assertFalse(r['phase2_started'])
        family.close.assert_called_once();family.begin_validation.assert_not_called();self.assertEqual(family.spawn.call_count,1)

    def test_cancelled_observer_cleans_and_never_launches_p2(self):
        code,r,family,identity,_=self.run_composition('observer')
        self.assertEqual(code,1);self.assertEqual(r['error_code'],'CANCELLED')
        family.close.assert_called_once();family.begin_validation.assert_not_called()

    def test_cancel_before_install_and_after_restart_never_launches_p2(self):
        # Each case needs an independent temporary composition root.
        for boundary in (7,8,9,10):
            with self.subTest(boundary=boundary):
                if (self.temp/'composition').exists():
                    import shutil;shutil.rmtree(self.temp/'composition')
                code,r,family,_,_=self.run_composition(boundary)
                self.assertEqual(code,1);self.assertTrue(r['cancelled']);self.assertFalse(r['phase2_started'])
                family.begin_validation.assert_not_called();family.close.assert_called_once()

    def test_preinstall_collision_never_dispatches_or_starts_p2(self):
        code,r,family,_,_=self.run_composition('profile')
        self.assertEqual(code,1);self.assertEqual(r['detail_code'],'PROFILE_COLLISION')
        family.configure_restart_images.assert_not_called();family.begin_validation.assert_not_called()

    def test_wrong_active_context_blocks_new_gui_and_p2(self):
        code,r,family,_,_=self.run_composition('context')
        self.assertEqual(code,1);self.assertEqual(r['detail_code'],'CONTEXT_MISMATCH')
        self.assertFalse(r['restart_context_verified']);family.begin_validation.assert_not_called()

    def test_cleanup_failure_cannot_start_p2(self):
        code,r,family,_,_=self.run_composition('cleanup')
        self.assertEqual(code,1);self.assertFalse(r['phase2_started']);family.begin_validation.assert_not_called()

    def test_deadline_record_failure_occurs_before_any_spawn(self):
        code,r,family,_,_=self.run_composition('deadline-write')
        self.assertEqual(code,1);self.assertEqual(r['registered_processes'],0);family.spawn.assert_not_called()


class RestartReceiptTests(unittest.TestCase):
    def value(self):
        return {'schema':1,'protocol':session.PROTOCOL,'status':'FRESH_VALIDATION_EXITED_NOT_ACCEPTANCE','operation':'COMPLETED',
                'error_code':'NONE','detail_code':'NONE','detail_step':'NONE','exception_class':'NONE','agreement_failure':None,'cancelled':False,'phase2_started':True,'phase2_exit':0,
                'preparation_cleanup':True,'validation_cleanup':True,'profile_verified':True,'restart_context_verified':True,
                'validation_context_verified':True,'restart_provenance':'OBSERVED_RESTARTER_EXEC','registered_processes':10,'course_acceptance':'NOT_RUN'}
    def test_valid_receipt_still_is_not_course_acceptance(self):session.validate_result(self.value())
    def test_all_unknown_cleanup_exit_and_context_combinations_fail_closed(self):
        for exit_code in (None,False,1,'0'):
            with self.subTest(exit_code=exit_code),self.assertRaises(ValueError):session.validate_result({**self.value(),'phase2_exit':exit_code})
        for field in ('preparation_cleanup','validation_cleanup','profile_verified','restart_context_verified','validation_context_verified'):
            for value in (False,None,1):
                with self.subTest(field=field,value=value),self.assertRaises(ValueError):session.validate_result({**self.value(),field:value})
    def test_cancel_or_nested_details_never_claim_success(self):
        for changes in ({'restart_provenance':'NONE'},{'restart_provenance':True},{'restart_provenance':{'command':'private'}},{'cancelled':True},{'detail_code':{'environment':'PRIVATE'}},{'operation':'private command'},
                        {'registered_processes':True},{'environment':{'private':'value'}}):
            with self.subTest(changes=changes),self.assertRaises((ValueError,TypeError)):session.validate_result({**self.value(),**changes})


def run_fixture(boundary):
    fixture=RestartHarness()
    fixture.setUp()
    try:return fixture.run_composition(boundary)
    finally:fixture.doCleanups()

if __name__=='__main__':unittest.main()
