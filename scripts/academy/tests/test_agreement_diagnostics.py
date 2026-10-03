"""Typed pre-request evidence, without GUI, legal network, or policy actions."""
from contextlib import ExitStack
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import plugin_agreement as plugin
import restart_session as session
from test_plugin_agreement import PluginFixture
from test_modal_window import proof_fixture
from test_restart_session import RestartHarness
import test_restart_session as restart_tests


class CheckpointDiagnostics(PluginFixture):
    def failed_checkpoint(self,step,error):
        proc=Mock();proc.poll.return_value=None
        identity=Mock();identity.metadata={'ide':{'pid':100}};identity.binding=self.root/'display-binding.properties'
        owned=Mock();progress={};actions=[]
        proof=proof_fixture(plugin.ACTIONS[5],self.window)
        def screen(action,dest,*_):
            actions.append(action)
            if step=='SNAPSHOT':raise error
            dest.write_bytes(self.image)
        with ExitStack() as stack:
            stack.enter_context(patch.object(plugin.trust,'context',side_effect=error if step=='CONTEXT' else None,return_value=self.context))
            stack.enter_context(patch.object(plugin,'verify_plugin',side_effect=error if step=='PLUGIN_BINARY' else None,return_value=plugin.PLUGIN_SHA))
            stack.enter_context(patch.object(plugin,'verify_legal',side_effect=error if step=='PDF_CHECK' else None,return_value=plugin.LEGAL_ID))
            if step=='MODAL_PROBE_BEFORE_SNAPSHOT':modal_side=error
            elif step=='MODAL_PROBE_AFTER_SNAPSHOT':modal_side=[proof,error]
            else:modal_side=None
            stack.enter_context(patch.object(plugin,'window_probe',side_effect=modal_side,return_value=proof))
            if step=='REQUEST_ENCODE':stack.enter_context(patch.object(plugin,'request_document',side_effect=error))
            stack.enter_context(patch.object(plugin.time,'monotonic',return_value=50))
            try:plugin.checkpoint(self.root,5,proc,screen,identity,owned,100,[],self.temp,{},progress=progress)
            except BaseException as exc:
                self.assertIs(exc,error)
                result=plugin.checkpoint_failure(progress,exc)
            else:self.fail('fixture did not stop')
        self.assertEqual(result['step'],step)
        self.assertEqual(result['request_state'],'NOT_ATTEMPTED');self.assertFalse(result['action_invoked'])
        self.assertFalse((self.root/'stage-5/request.json').exists())
        self.assertNotIn(plugin.ACTIONS[5],actions)
        return result

    def failed_result(self,diagnostic):
        return {**restart_tests.RestartReceiptTests().value(),'status':'FAILED','operation':'AGREEMENTS',
            'error_code':'UNEXPECTED_ERROR','exception_class':diagnostic['exception_class'],
            'agreement_failure':diagnostic,'phase2_started':False,'phase2_exit':None,
            'profile_verified':False,'restart_context_verified':False,'validation_context_verified':False,
            'validation_cleanup':None,'restart_provenance':'NONE','cancelled':True}

    def test_exact_pre_request_boundaries_and_exception_classes(self):
        for step,error in [('CONTEXT',ValueError('PRIVATE_CONTEXT')),('PLUGIN_BINARY',ImportError('PRIVATE_PATH')),
            ('PDF_CHECK',subprocess.CalledProcessError(7,['PRIVATE_COMMAND'],stderr=b'PRIVATE_ENV')),
            ('MODAL_PROBE_BEFORE_SNAPSHOT',plugin.ModalProbeFailure(2)),
            ('SNAPSHOT',AttributeError('PRIVATE_PATH')),
            ('MODAL_PROBE_AFTER_SNAPSHOT',subprocess.TimeoutExpired('PRIVATE_COMMAND',2)),
            ('REQUEST_ENCODE',TypeError('PRIVATE_OBJECT'))]:
            with self.subTest(step=step):
                # Fixtures are independent; no completed/request data is reused.
                if (self.root/'stage-5').exists():
                    import shutil;shutil.rmtree(self.root/'stage-5')
                diagnostic=self.failed_checkpoint(step,error)
                self.assertEqual(diagnostic['exception_class'],type(error).__name__)
                self.assertNotIn(b'PRIVATE_',plugin.encode(diagnostic))
                session.validate_result(self.failed_result(diagnostic))

    def test_known_modal_failure_reaches_existing_collector_before_request(self):
        document=plugin.modal_window.failure_from_exception(plugin.modal_window.ProofError())
        diagnostic=self.failed_checkpoint('MODAL_PROBE_BEFORE_SNAPSHOT',plugin.ModalProbeFailure(2,document))
        self.write(self.root/session.RESULT,self.failed_result(diagnostic))
        self.assertEqual(json.loads(session.collect(self.root))['agreement_failure'],diagnostic)
        from collect_evidence import collect
        (self.run/'evidence/validate.stderr.log').write_text('safe existing log\n')
        out=self.temp/'artifact';collect(self.run,out,ui_root=self.root,job_status='failure',cleanup_exit=0)
        self.assertEqual(json.loads((out/session.RESULT).read_text())['agreement_failure']['modal_failure'],document)
        self.assertTrue((out/'validate.stderr.log').exists());self.assertFalse((out/'plugin-stage-5-request.json').exists())

    def test_cancellation_propagates_without_snapshot_or_request(self):
        diagnostic=self.failed_checkpoint('PDF_CHECK',InterruptedError('PRIVATE_CANCEL'))
        self.assertEqual(diagnostic['reason'],'CANCELLED')

    def test_replayed_context_rejected_by_existing_collector(self):
        diagnostic=self.failed_checkpoint('PDF_CHECK',TimeoutError())
        diagnostic['context']['tested_sha']='f'*40
        self.write(self.root/session.RESULT,self.failed_result(diagnostic))
        with self.assertRaises(ValueError):session.collect(self.root)

    def test_nested_unknown_bool_and_oversized_diagnostics_rejected(self):
        diagnostic=self.failed_checkpoint('PDF_CHECK',ValueError())
        for key,value in [('step',{'environment':'PRIVATE'}),('exception_class','PRIVATE_CLASS'),
            ('probe_exit_code',False),('probe_exit_code',0),('probe_exit_code',256),('context',{'command':'PRIVATE'}),
            ('request_state',1),('action_invoked',True),('modal_failure',{'nested':{'environment':'PRIVATE'}}),
            ('reason','X'*100000),('schema',True),('stage',True)]:
            with self.subTest(key=key),self.assertRaises((ValueError,TypeError)):
                plugin.checkpoint_failure_document({**diagnostic,key:value})
        with self.assertRaises(ValueError):plugin.checkpoint_failure_document({**diagnostic,'environment':'PRIVATE'})

    def test_malformed_diagnostic_preserves_other_safe_evidence(self):
        diagnostic=self.failed_checkpoint('PDF_CHECK',ValueError())
        diagnostic['step']={'command':'PRIVATE_COMMAND','environment':'PRIVATE_ENV'}
        self.write(self.root/session.RESULT,self.failed_result(diagnostic))
        (self.run/'evidence/validate.stderr.log').write_text('safe\n')
        from collect_evidence import collect
        out=self.temp/'artifact';collect(self.run,out,ui_root=self.root,job_status='failure',cleanup_exit=0)
        self.assertFalse((out/session.RESULT).exists());self.assertTrue((out/'validate.stderr.log').exists())
        for path in out.iterdir():self.assertNotIn(b'PRIVATE_',path.read_bytes())


class ProbeDiagnostics(unittest.TestCase):
    def test_nonzero_probe_retains_only_valid_bounded_document(self):
        document=plugin.modal_window.failure_from_exception(plugin.modal_window.ProofError())
        runner=Mock(return_value=subprocess.CompletedProcess(['PRIVATE_COMMAND'],2,plugin.encode(document)))
        with self.assertRaises(plugin.ModalProbeFailure) as raised:plugin.window_probe(100,plugin.ACTIONS[5],{},runner)
        self.assertEqual(raised.exception.document,document);self.assertEqual(raised.exception.exit_code,2)
        self.assertFalse(runner.call_args.kwargs['check']);self.assertEqual(runner.call_args.kwargs['timeout'],2)
        self.assertEqual(runner.call_args.kwargs['stderr'],subprocess.DEVNULL)

    def test_arbitrary_child_output_never_enters_diagnostic(self):
        for raw in (b'PRIVATE_STDERR',b'{"environment":{"X":"PRIVATE"}}',b'X'*2049,b'{"schema":1,"schema":1}'):
            runner=Mock(return_value=subprocess.CompletedProcess(['PRIVATE'],7,raw))
            with self.assertRaises(plugin.ModalProbeFailure) as raised:plugin.window_probe(100,plugin.ACTIONS[5],{},runner)
            self.assertEqual(raised.exception.exit_code,7);self.assertIsNone(raised.exception.document)

    def test_success_still_requires_original_exact_proof(self):
        proof=proof_fixture()
        runner=Mock(return_value=subprocess.CompletedProcess(['fixture'],0,plugin.encode(proof)))
        self.assertEqual(plugin.window_probe(100,plugin.ACTIONS[5],{},runner),proof)
        proof['root_children'][0]['x']=-1
        with self.assertRaises(ValueError):plugin.window_probe(100,plugin.ACTIONS[5],{},Mock(return_value=subprocess.CompletedProcess([],0,plugin.encode(proof))))

    def test_real_child_invalid_display_returns_typed_failure_without_x_connection(self):
        result=subprocess.run([sys.executable,plugin.__file__,'observe-window','--pid','100','--stage','5'],
            env={'PATH':os.defpath,'LANG':'C.UTF-8','DISPLAY':'INVALID_PRIVATE_VALUE'},capture_output=True,timeout=5)
        self.assertEqual(result.returncode,2)
        plugin.modal_window.failure_document(plugin.json_read(result.stdout))
        self.assertEqual(result.stderr,b'');self.assertNotIn(b'PRIVATE',result.stdout)


class SessionDiagnostics(RestartHarness):
    def run_failure(self,cleanup_failure=False):
        original=session.plugin.checkpoint
        def failing(*args,**kwargs):
            if cleanup_failure:args[5].close.side_effect=RuntimeError('PRIVATE_CLEANUP')
            # Use the actual checkpoint and marker transitions; only external legal/binary
            # dependencies are fixtures. Failure is before any window/GUI subprocess.
            with patch.object(plugin,'verify_plugin',return_value=plugin.PLUGIN_SHA),patch.object(plugin,'verify_legal',side_effect=subprocess.CalledProcessError(9,'PRIVATE_COMMAND')):
                return original(*args,**kwargs)
        # run_composition's stub is replaced with this real checkpoint at its patch site.
        with patch.object(session.plugin,'checkpoint',side_effect=failing) as checkpoint:
            self._diagnostic_checkpoint=checkpoint
            code,value,family,_,_=self.run_composition('real-plugin-failure')
        self.assertEqual(code,1);self.assertEqual(value['agreement_failure']['step'],'PDF_CHECK')
        self.assertEqual(value['agreement_failure']['probe_exit_code'],9)
        self.assertEqual(value['exception_class'],'CalledProcessError')
        family.close.assert_called_once();family.begin_validation.assert_not_called()
        self.assertFalse(value['phase2_started']);self.assertNotIn('PRIVATE',json.dumps(value))
        return value

    def test_first_plugin_exception_survives_cleanup_with_no_p2(self):
        self.run_failure()

    def test_cleanup_failure_keeps_first_plugin_exception(self):
        value=self.run_failure(True)
        self.assertFalse(value['preparation_cleanup'])
        self.assertEqual(value['detail_code'],'FAMILY_CLEANUP_INCOMPLETE')
        self.assertEqual(value['agreement_failure']['reason'],'SUBPROCESS_EXIT')

if __name__=='__main__':unittest.main()
