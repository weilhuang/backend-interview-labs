"""Bounded synthetic /proc task views and one real child; no JVM or large thread set."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import Mock, patch

BASE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(BASE))
import ui_session as session
import collect_evidence as evidence

PARENT={'pid':1234,'ppid':77,'pgrp':1234,'session':1234,'start_time':'12345','uid':1000}


class TaskViewTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)

    def view(self,parent,count,value=''):
        root=self.root/str(parent['pid'])/'task';root.mkdir(parents=True)
        for n in range(count):
            path=root/str(n+1);path.mkdir();(path/'children').write_text(value)
        return root

    def routed(self,value):
        path=Path(value)
        self.assertEqual(path.parts[1],'proc')
        self.assertEqual(path.parts[-1],'task')
        self.assertEqual(len(path.parts),4)
        return self.root/path.parts[2]/'task'

    def failure(self,parent,deadline,clock):
        with patch.object(session,'Path',side_effect=self.routed),patch.object(session.time,'monotonic',side_effect=clock):
            with self.assertRaises(RuntimeError) as raised:session.direct_candidates(parent,deadline)
        doc=session.exception_diagnostic(raised.exception,'SCAN_OWNED')
        clean=evidence.supervisor_document({'schema_version':1,'status':'FAILED','error_details':doc},'result.json')
        self.assertEqual(clean['error_details'],doc)
        return raised.exception,doc

    def test_zero_and_exact_1024_tasks_are_complete_without_limit_change(self):
        for count in (0,1024):
            parent={**PARENT,'pid':1234+count};self.view(parent,count,'2000 2000')
            with patch.object(session,'Path',side_effect=self.routed),patch.object(session.time,'monotonic',return_value=1):
                self.assertEqual(session.direct_candidates(parent,60),{2000} if count else set())

    def test_1025th_entry_rejected_before_read_and_count_branch_precedes_deadline(self):
        self.view(PARENT,1025,'2000')
        # The first1,024 guard samples are within budget; the failure sample is expired.
        _,doc=self.failure(PARENT,60,[1]+[2]*1024+[61])
        self.assertEqual(doc['code'],'TASK_ENTRY_LIMIT')
        facts=doc['scan_facts'];self.assertEqual(facts['task_entries_observed'],1025)
        self.assertEqual(facts['child_candidates_seen'],1);self.assertTrue(facts['deadline_expired'])
        self.assertEqual(facts['elapsed_monotonic_ns'],60_000_000_000)
        self.assertEqual(facts['parent_identity_check'],'CALLER_SUPPLIED')

    def test_deadline_branch_records_exact_original_deadline(self):
        self.view(PARENT,1,'not-an-integer-must-not-be-read')
        _,doc=self.failure(PARENT,2,[1,2])
        self.assertEqual(doc['code'],'SCAN_DEADLINE')
        self.assertEqual(doc['scan_facts']['task_entries_observed'],1)
        self.assertEqual(doc['scan_facts']['deadline_monotonic_ns'],2_000_000_000)

    def test_count_is_reset_for_each_verified_parent(self):
        other={**PARENT,'pid':2345};self.view(PARENT,600);self.view(other,600)
        owned=session.Owned(60);owned.members={PARENT['pid']:(PARENT,8),other['pid']:(other,9)}
        with patch.object(session,'Path',side_effect=self.routed),patch.object(session,'matching',return_value=True),patch.object(session.time,'monotonic',return_value=1):
            owned.scan()
        self.assertEqual(len(owned.members),2)

    def test_birth_hash_changes_and_no_raw_identity_or_private_text_is_projected(self):
        a=session.child_scan_error(PARENT,60,1,2,1025,set(),'TASK_ENTRY_LIMIT')
        b=session.child_scan_error({**PARENT,'start_time':'12346'},60,1,2,1025,set(),'TASK_ENTRY_LIMIT')
        self.assertNotEqual(a.scan_facts['parent_identity_sha256'],b.scan_facts['parent_identity_sha256'])
        raw=json.dumps(session.exception_diagnostic(a,'SCAN_OWNED'))
        for forbidden in ('"pid"','"ppid"','"uid"','"start_time"','/proc/','command','environment'):
            self.assertNotIn(forbidden,raw)

    def test_owned_parent_match_is_required_before_discovery_and_classifies_failure(self):
        parent={**PARENT,'ppid':os.getpid()};owned=session.Owned(60)
        owned.members={parent['pid']:(parent,8)}
        exc=session.child_scan_error(parent,60,1,2,1025,set(),'TASK_ENTRY_LIMIT')
        with patch.object(session,'matching',return_value=False),patch.object(session,'direct_candidates') as discover,patch.object(session.time,'monotonic',return_value=1):
            owned.scan();discover.assert_not_called()
        with patch.object(session,'matching',return_value=True),patch.object(session,'direct_candidates',side_effect=exc),patch.object(session.time,'monotonic',return_value=1):
            with self.assertRaises(RuntimeError):owned.scan()
        self.assertEqual(exc.scan_facts['parent_role'],'DIRECT_CHILD')
        self.assertEqual(exc.scan_facts['parent_identity_check'],'MATCHED_BEFORE_SCAN')

    def test_cancellation_remains_cancellation_without_partial_candidates(self):
        self.view(PARENT,2)
        with patch.object(session,'Path',side_effect=self.routed),patch.object(session.time,'monotonic',side_effect=[1,InterruptedError('fixture')]):
            with self.assertRaises(InterruptedError):session.direct_candidates(PARENT,60)

    def test_preexisting_or_guard_and_split_guard_make_same_bounded_decisions(self):
        # This explicit old decision is retained as the regression oracle, with
        # the same per-parent1024/candidate512 limits and pre-read guard order.
        def previous(parent,deadline):
            tasks=self.routed(f"/proc/{parent['pid']}/task");result=set();count=0
            for task in tasks.iterdir():
                count+=1
                if count>1024 or 1>=deadline:raise RuntimeError('budget')
                value=(task/'children').read_text()
                if len(value)>65536:raise RuntimeError('metadata')
                result.update(int(word) for word in value.split())
                if len(result)>512:raise RuntimeError('children')
            return result
        for count in (0,1,1024,1025):
            parent={**PARENT,'pid':5000+count};self.view(parent,count,'2000')
            for deadline in (0,1,2):
                outcomes=[]
                for fn in (previous,session.direct_candidates):
                    with patch.object(session,'Path',side_effect=self.routed),patch.object(session.time,'monotonic',return_value=1):
                        try:outcomes.append(('RETURN',fn(parent,deadline)))
                        except RuntimeError:outcomes.append(('REJECT',None))
                self.assertEqual(outcomes[0],outcomes[1],(count,deadline))


class PublicProjectionTests(unittest.TestCase):
    def facts(self):
        return session.child_scan_error(PARENT,60,1,2,1025,set(),'TASK_ENTRY_LIMIT').scan_facts

    def test_nested_payloads_type_confusion_and_false_branch_facts_reject(self):
        mutations={'task_entries_observed':[True,1024,1026,{}],
            'task_entry_limit':[True,2048], 'child_candidates_seen':[True,513,-1],
            'sampled_monotonic_ns':[True,-1,2**63,{'command':'PRIVATE'}],
            'deadline_monotonic_ns':[float('nan'),'PRIVATE'],
            'elapsed_monotonic_ns':[True,0], 'deadline_expired':[1,'false',True],
            'parent_identity_sha256':['PRIVATE',{'environment':'PRIVATE'}],
            'parent_role':['PRIVATE',{}], 'parent_identity_check':['MATCHED_BEFORE_SCAN',{}]}
        for key,values in mutations.items():
            for value in values:
                with self.subTest(key=key,value=value),self.assertRaises(ValueError):
                    evidence.scan_facts_document({**self.facts(),key:value},'TASK_ENTRY_LIMIT')
        with self.assertRaises(ValueError):evidence.scan_facts_document({**self.facts(),'private':'PRIVATE'*100000},'TASK_ENTRY_LIMIT')
        with self.assertRaises(ValueError):evidence.scan_facts_document(self.facts(),'SCAN_DEADLINE')

    def test_new_codes_require_exact_facts_and_no_success_can_be_inferred(self):
        doc={'schema_version':1,'status':'FAILED','error_details':{'operation':'SCAN_OWNED',
             'exception_type':'RuntimeError','code':'TASK_ENTRY_LIMIT','scan_facts':self.facts()}}
        clean=evidence.supervisor_document(doc,'result.json')
        self.assertIsNone(clean['exit_code']);self.assertIsNone(clean['cleanup_verified'])
        self.assertFalse(evidence.verified_supervisor_success(clean,'success',0))
        del doc['error_details']['scan_facts']
        with self.assertRaises(ValueError):evidence.supervisor_document(doc,'result.json')

    def test_first_scan_cause_survives_cleanup_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);session.put(root/'state.json',session.budget_record(session.process_info(os.getpid()),3600))
            original=session.child_scan_error(PARENT,60,1,2,1025,set(),'TASK_ENTRY_LIMIT')
            owned=Mock();owned.members={1:(PARENT,9)};owned.scan.side_effect=original
            owned.stop.side_effect=RuntimeError('已登记进程未全部退出')
            proc=Mock();proc.poll.return_value=None;proc.wait.return_value=-15
            with patch.object(session,'Owned',return_value=owned),patch.object(session.subprocess,'Popen',return_value=proc),patch.object(session.signal,'signal'):
                self.assertEqual(session.worker(root,['fixture']),1)
            value=evidence.supervisor_document(json.loads((root/'result.json').read_text()),'result.json')
            self.assertEqual(value['error_details']['code'],'TASK_ENTRY_LIMIT')
            self.assertEqual(value['cleanup_error_details']['code'],'REGISTERED_CLEANUP_INCOMPLETE')
            self.assertFalse(value['cleanup_verified'])

    def test_malformed_scan_projection_is_omitted_while_other_safe_logs_survive(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);run=root/'run';(run/'evidence').mkdir(parents=True);ui=root/'ui';ui.mkdir()
            bad=self.facts();bad['sampled_monotonic_ns']={'environment':'SYNTHETIC_PRIVATE'}
            (ui/'result.json').write_text(json.dumps({'schema_version':1,'status':'FAILED',
                'error_details':{'operation':'SCAN_OWNED','exception_type':'RuntimeError',
                    'code':'TASK_ENTRY_LIMIT','scan_facts':bad}}))
            (ui/'supervisor.log').write_text('safe owned log\n')
            out=root/'out';evidence.collect(run,out,ui_root=ui,job_status='failure',cleanup_exit=0)
            self.assertFalse((out/'supervisor-result.json').exists())
            self.assertTrue((out/'supervisor.log').exists())
            for path in out.iterdir():self.assertNotIn(b'SYNTHETIC_PRIVATE',path.read_bytes())

    def test_long_uptime_projection_uses_one_consistent_integer_difference(self):
        exc=session.child_scan_error(PARENT,100000000.9,100000000.1,100000000.3,1025,set(),'TASK_ENTRY_LIMIT')
        facts=evidence.scan_facts_document(exc.scan_facts,'TASK_ENTRY_LIMIT')
        self.assertEqual(facts['elapsed_monotonic_ns'],facts['sampled_monotonic_ns']-facts['scan_started_monotonic_ns'])

    def test_real_child_identity_and_proc_task_read_are_bounded_and_cleaned(self):
        spawn_before=time.monotonic()
        child=subprocess.Popen([sys.executable,'-B','-c','import time;time.sleep(10)'],start_new_session=True)
        deadline=time.monotonic()+5;owned=session.Owned(deadline)
        try:
            meta=owned.register_root(child)
            self.assertTrue(session.matching(meta,owned.members[child.pid][1]))
            record=session.budget_record(meta,3600)
            expected=int(meta['start_time'])/os.sysconf('SC_CLK_TCK')+3600
            with tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);session.put(root/'state.json',record)
                self.assertEqual(session.read_outer_deadline(root),expected)
                self.assertEqual(session.checked_budget(record,3600,session.process_info(child.pid)),expected)
            # Local fresh-child observation only, not evidence of the prior runner's clock.
            tick=1/os.sysconf('SC_CLK_TCK')
            self.assertGreaterEqual(expected-3600,spawn_before-2*tick)
            self.assertLessEqual(expected-3600,time.monotonic()+2*tick)
            self.assertEqual(session.direct_candidates(meta,time.monotonic()+2),set())
            self.assertEqual(owned.deadline,deadline)
        finally:
            owned.stop();child.wait(timeout=1)
        self.assertIsNotNone(child.returncode)


if __name__=='__main__':unittest.main()
