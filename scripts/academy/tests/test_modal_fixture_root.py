"""Exact synthetic root and cleanup regressions; all X/process calls are mocked."""
import copy
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import unittest
from contextlib import ExitStack
from unittest.mock import Mock, call, patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import modal_fixture as fixture
from test_modal_window import proof_fixture, _record

ACTION='CHECK_ACADEMY_PLUGIN_ONLY'
ROOT=10
WINDOW=91


def root_proof():
    proof=proof_fixture()
    proof['root_children'].append(_record(WINDOW,-100,-100,10,10,window_class=2,map_state=0))
    return proof


class ExactSyntheticRoot(unittest.TestCase):
    def setUp(self):
        self.x=Mock()
        self.x.XCreateWindow.return_value=WINDOW
        self.cases=[]
        self.now=100
        self.clock=patch.object(fixture.time,'monotonic',side_effect=lambda:self.now)
        self.clock.start()
        self.addCleanup(self.clock.stop)

    def run_case(self,observe):
        fixture.negative_unmapped_root_case(self.x,1,ROOT,observe,ACTION,self.cases,100)

    def test_exact_owned_root_remains_unmapped_and_is_destroyed_after_pass(self):
        observed=Mock(return_value=root_proof())
        def destroyed(connection,window):
            self.assertEqual(self.cases,[{'case':'negative_unmapped_input_only_root','status':'PASS'}])
        self.x.XDestroyWindow.side_effect=destroyed
        self.run_case(observed)
        self.assertEqual(self.x.mock_calls,[
            call.XCreateWindow(1,ROOT,-100,-100,10,10,0,0,2,None,0,None),
            call.XSync(1,False),call.XDestroyWindow(1,WINDOW),call.XSync(1,False)])
        observed.assert_called_once_with()

    def test_exact_id_geometry_class_map_state_and_complete_proof_required(self):
        changes=({'window_id':92},{'x':-99},{'y':-99},{'width':11},{'height':11},
                 {'border':1},{'window_class':1},{'map_state':2},{'map_state':False})
        for update in changes:
            with self.subTest(update=update):
                self.x.reset_mock();proof=root_proof();proof['root_children'][-1].update(update)
                with self.assertRaises(ValueError):self.run_case(lambda:proof)
                self.assertEqual(self.cases,[])
                self.x.XDestroyWindow.assert_called_once_with(1,WINDOW)
                self.assertEqual(self.x.XSync.call_count,2)
        for change in (lambda p:p.pop('target_route'),
                       lambda p:p.__setitem__('target_route',[999]),
                       lambda p:p.__setitem__('focus_path',[WINDOW]),
                       lambda p:p['root_children'].pop(),
                       lambda p:p['root_children'].append(copy.deepcopy(p['root_children'][-1]))):
            with self.subTest(change=change):
                self.x.reset_mock();proof=root_proof();change(proof)
                with self.assertRaises(ValueError):self.run_case(lambda:proof)
                self.assertEqual(self.cases,[])
                self.x.XDestroyWindow.assert_called_once_with(1,WINDOW)

    def test_creation_and_observation_failures_do_not_invent_pass(self):
        self.x.XCreateWindow.return_value=0
        with self.assertRaises(ValueError):self.run_case(Mock())
        self.x.XSync.assert_not_called();self.x.XDestroyWindow.assert_not_called()
        self.x.XCreateWindow.return_value=WINDOW
        with self.assertRaises(subprocess.TimeoutExpired):
            self.run_case(Mock(side_effect=subprocess.TimeoutExpired('mock-observer',2)))
        self.assertEqual(self.cases,[])
        self.x.XDestroyWindow.assert_called_once_with(1,WINDOW)
        self.assertEqual(self.x.XSync.call_count,2)

    def test_cancellation_during_observation_starts_no_cleanup_roundtrip(self):
        with self.assertRaises(InterruptedError):
            self.run_case(Mock(side_effect=InterruptedError('CANCELLED')))
        self.assertEqual(self.cases,[])
        self.x.XDestroyWindow.assert_not_called()
        self.x.XSync.assert_called_once_with(1,False)

    def test_expired_budget_or_alarm_never_starts_cleanup_roundtrip(self):
        for moment in (145,150):
            with self.subTest(moment=moment):
                self.now=100;self.x.reset_mock()
                def observe():
                    self.now=moment
                    return root_proof()
                with self.assertRaises(ValueError):self.run_case(observe)
                self.assertEqual(self.cases,[])
                self.x.XDestroyWindow.assert_not_called()
                self.x.XSync.assert_called_once_with(1,False)

    def test_no_sync_after_destroy_is_cancelled_or_exhausts_budget(self):
        for interrupted in (False,True):
            with self.subTest(interrupted=interrupted):
                self.now=100;self.x.reset_mock();self.cases=[]
                def destroyed(*_):
                    self.now=150
                    if interrupted:raise InterruptedError('CANCELLED')
                self.x.XDestroyWindow.side_effect=destroyed
                with self.assertRaises(InterruptedError if interrupted else ValueError):
                    self.run_case(lambda:root_proof())
                self.x.XDestroyWindow.assert_called_once_with(1,WINDOW)
                self.x.XSync.assert_called_once_with(1,False)


class OwnedXvfbFallback(unittest.TestCase):
    def run_fixture(self,problem=None,missing_pidfd=False,wait_timeout=False):
        x=Mock();x.XOpenDisplay.return_value=1;x.XDefaultRootWindow.return_value=ROOT
        x.XCreateSimpleWindow.side_effect=[40,56,57,58,59,60,61]
        x.XCreateWindow.side_effect=[WINDOW,92]
        server=Mock(pid=4242);server.poll.return_value=None
        if wait_timeout:server.wait.side_effect=[subprocess.TimeoutExpired('mock-xvfb',3),-9]
        now=[100];cutoff=[];observations=[]
        changed=proof_fixture();changed['focus_revert']=1
        replies=[proof_fixture(),root_proof(),proof_fixture(),None,None,None,proof_fixture(),changed,None]
        def observe(argv,**kwargs):
            observations.append((argv,kwargs))
            if len(observations)==2 and problem:
                if problem=='cancelled':
                    cutoff.append(len(x.mock_calls));raise InterruptedError('CANCELLED')
                if problem=='expired':
                    now[0]=150;cutoff.append(len(x.mock_calls))
                if problem=='invalid':replies[1]['root_children'][-1]['window_id']=92
            proof=replies[len(observations)-1]
            return subprocess.CompletedProcess(argv,1 if proof is None else 0,
                                               b'' if proof is None else json.dumps(proof).encode(),b'')
        with tempfile.TemporaryDirectory() as tmp,ExitStack() as stack:
            temp=Mock(name=tmp);temp.name=tmp
            for target,value in ((fixture.tempfile,'TemporaryDirectory'),(fixture.C,'CDLL'),
                                 (fixture.subprocess,'Popen'),(fixture.subprocess,'run'),
                                 (fixture.signal,'signal'),(fixture.signal,'alarm'),
                                 (fixture.signal,'pidfd_send_signal'),(fixture.os,'pidfd_open'),
                                 (fixture.os,'close'),(fixture,'publish')):
                mock=stack.enter_context(patch.object(target,value))
                if value=='TemporaryDirectory':mock.return_value=temp
                elif value=='CDLL':mock.return_value=x
                elif value=='Popen':mock.return_value=server
                elif value=='run':mock.side_effect=observe
                elif value=='pidfd_open':
                    if missing_pidfd:mock.side_effect=OSError('mock pidfd unavailable')
                    else:mock.return_value=99
                elif value=='alarm':alarm=mock
                elif value=='pidfd_send_signal':send_signal=mock
                elif value=='publish':publish=mock
            stack.enter_context(patch.object(fixture,'BINARY',Mock(is_file=lambda:True,is_symlink=lambda:False)))
            stack.enter_context(patch.object(fixture.Path,'exists',return_value=False))
            stack.enter_context(patch.object(fixture.time,'monotonic',side_effect=lambda:now[0]))
            stack.enter_context(patch.dict(os.environ,{'GITHUB_RUN_ID':'123','GITHUB_RUN_ATTEMPT':'1','GITHUB_SHA':'a'*40}))
            if problem or missing_pidfd:
                with self.assertRaises(SystemExit) as stopped:fixture.main(Path(tmp)/'report.json')
                self.assertEqual(stopped.exception.code,1)
            else:fixture.main(Path(tmp)/'report.json')
            report=json.loads(publish.call_args.args[1])
            self.assertEqual(alarm.call_args_list,[call(50),call(0)])
            x.XCloseDisplay.assert_not_called()
        return report,x,server,send_signal,observations,cutoff

    def test_success_runs_all_cases_and_keeps_original_observer_limit(self):
        report,x,server,send_signal,observations,_=self.run_fixture()
        self.assertEqual(report['status'],'PASS');self.assertEqual(report['cleanup'],'REAPED')
        self.assertEqual([item['case'] for item in report['cases']],list(fixture.CASE_NAMES))
        self.assertEqual(len(observations),9)
        for argv,kwargs in observations:
            self.assertIn('modal_window.observe',argv[3]);self.assertEqual(kwargs['timeout'],2)
        created=x.mock_calls.index(call.XCreateWindow(1,ROOT,-100,-100,10,10,0,0,2,None,0,None))
        destroyed=x.mock_calls.index(call.XDestroyWindow(1,WINDOW))
        overlay=x.mock_calls.index(call.XCreateSimpleWindow(1,ROOT,400,400,30,30,0,0,0x444444))
        self.assertLess(created,destroyed);self.assertLess(destroyed,overlay)
        self.assertEqual(x.mock_calls[destroyed+1],call.XSync(1,False))
        self.assertNotIn(call.XMapWindow(1,WINDOW),x.mock_calls)
        send_signal.assert_called_once_with(99,signal.SIGTERM);server.wait.assert_called_once_with(timeout=3)

    def test_cancelled_and_expired_cases_fail_with_owned_reap_and_no_x_calls(self):
        for problem,error in (('cancelled','CANCELLED'),('expired','PROOF_OR_FIXTURE_FAILED')):
            with self.subTest(problem=problem):
                report,x,server,send_signal,_,cutoff=self.run_fixture(problem)
                self.assertEqual((report['status'],report['error'],report['cleanup']),('FAIL',error,'REAPED'))
                self.assertEqual(len(report['cases']),1)
                self.assertEqual(x.mock_calls[cutoff[0]:],[])
                send_signal.assert_called_once_with(99,signal.SIGTERM)
                server.wait.assert_called_once_with(timeout=3)

    def test_failed_proof_destroys_exact_root_then_reaps_owned_server(self):
        report,x,server,send_signal,_,_=self.run_fixture('invalid',wait_timeout=True)
        self.assertEqual((report['status'],report['cleanup']),('FAIL','REAPED'))
        self.assertEqual(len(report['cases']),1)
        x.XDestroyWindow.assert_called_once_with(1,WINDOW)
        self.assertEqual(x.mock_calls[-1],call.XSync(1,False))
        self.assertEqual(send_signal.call_args_list,[call(99,signal.SIGTERM),call(99,signal.SIGKILL)])
        self.assertEqual(server.wait.call_args_list,[call(timeout=3),call(timeout=2)])

    def test_existing_direct_child_fallback_terminates_and_kills_only_owned_server(self):
        report,x,server,send_signal,_,_=self.run_fixture(missing_pidfd=True,wait_timeout=True)
        self.assertEqual((report['status'],report['cleanup']),('FAIL','REAPED'))
        self.assertEqual(report['cases'],[]);self.assertEqual(x.mock_calls,[])
        send_signal.assert_not_called();server.terminate.assert_called_once_with();server.kill.assert_called_once_with()
        self.assertEqual(server.wait.call_args_list,[call(timeout=3),call(timeout=2)])


if __name__=='__main__':unittest.main()
