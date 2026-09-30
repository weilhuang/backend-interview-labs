import copy
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from plan import SUITES, COURSE_ROOTS, SERVICE_SUITES, affected_suites, event_range, make_plan, validate_inventory
from finish import finish

HEAD='a'*40
BASE='b'*40
EVENT={'action':'synchronize','pull_request':{'number':1,'head':{'sha':HEAD,'repo':{'full_name':'owner/course'}},'base':{'sha':BASE},'labels':[]}}
ENV={'GITHUB_RUN_ID':'200','GITHUB_RUN_ATTEMPT':'1'}


def plan(**kwargs):
    args=dict(changed=['courses/messaging/src/A.java'],event_name='pull_request',event=EVENT,
              repository='owner/course',tested_sha='c'*40)
    args.update(kwargs)
    return make_plan(**args)


def results(**kwargs):
    value={s:{'result':'skipped'} for s in SUITES}
    value.update(plan={'result':'success'},static={'result':'success'})
    value.update({key:{'result':status} for key,status in kwargs.items()})
    return value


class DependencyTests(unittest.TestCase):
    def test_markdown_only_runs_full_static_contracts(self):
        for path in ['README.md','docs/environment/README.md','courses/messaging/task.md']:
            self.assertEqual(affected_suites(path),set())

    def test_each_course_and_shared_pilot(self):
        for suite,roots in SUITES.items():
            for root in roots:
                expected={suite}
                if root=='courses/java-recovery-collections/':expected.add('lab-environment')
                self.assertEqual(affected_suites(root+'src/A.java'),expected)

    def test_locks_metadata_authoring_and_scripts_are_real_dependencies(self):
        for suffix in ['authoring/verify.py','task-info.yaml','gradle.lockfile','scripts/check.py',
                       'gradlew','gradle/wrapper/gradle-wrapper.properties','authoring/requirements.txt']:
            self.assertEqual(affected_suites('courses/messaging/'+suffix),{'messaging'})

    def test_shared_infra_fans_out(self):
        for suffix in ['versions.env','compose.yaml','testcontainers/LabImages.java','rocketmq/start.sh']:
            self.assertEqual(affected_suites('infra/'+suffix),SERVICE_SUITES)

    def test_shared_known_scripts_have_explicit_consumers(self):
        self.assertEqual(affected_suites('scripts/sync_course_versions.py'),{'data-storage','java-frameworks','lab-environment'})
        self.assertEqual(affected_suites('scripts/lab.py'),{'lab-environment'})

    def test_unknown_shared_scripts_and_course_are_full(self):
        for path in ['scripts/new_shared_judge.py','courses/new-course/src/A.java','new.lock','other/asset.png']:
            self.assertEqual(affected_suites(path),set(SUITES))

    def test_workflow_scope(self):
        self.assertEqual(affected_suites('.github/workflows/messaging.yml'),{'messaging'})
        for path in ['scripts/ci/plan.py','.github/workflows/ci.yml','.github/workflows/new.yml']:
            self.assertEqual(affected_suites(path),set(SUITES))

    def test_quality_runtime_changes_revalidate_all_real_gates(self):
        self.assertEqual(affected_suites('scripts/quality/academy_gate.py'),set(SUITES))

    def test_inventory_rejects_unknown_or_missing_course(self):
        known=[f'courses/{name}/course-info.yaml' for name in COURSE_ROOTS]
        self.assertFalse(validate_inventory(known))
        self.assertTrue(validate_inventory(known+['courses/new-course/course-info.yaml']))
        self.assertTrue(validate_inventory(known[1:]))


class DecisionTests(unittest.TestCase):
    def test_docs_only_pr_has_no_heavy_jobs(self):
        self.assertTrue(all(r['decision']=='not-required' for r in plan(changed=['README.md'])['suites'].values()))

    def test_cumulative_code_pr_still_runs_after_docs_commit(self):
        p=plan(changed=['README.md','courses/messaging/A.java','courses/java-foundations/F.java'])
        self.assertEqual({s for s,r in p['suites'].items() if r['decision']=='run'},{'messaging','java-foundations'})

    def test_fork_and_same_repo_pr_use_same_conservative_scope(self):
        fork=copy.deepcopy(EVENT);fork['pull_request']['head']['repo']['full_name']='fork/course'
        self.assertEqual(plan(event=fork)['suites'],plan()['suites'])

    def test_manual_release_main_and_full_label_force_full(self):
        cases=[('workflow_dispatch',{}),('release',{}),('push',{}),
               ('pull_request',dict(EVENT,action='labeled',label={'name':'ci:full'}))]
        for name,event in cases:
            p=plan(event_name=name,event=event)
            self.assertTrue(p['full'])
            self.assertTrue(all(row['decision']=='run' for row in p['suites'].values()))

    def test_full_label_remains_full_until_removed(self):
        event=copy.deepcopy(EVENT);event['pull_request']['labels']=[{'name':'ci:full'}]
        self.assertTrue(plan(event=event,changed=['README.md'])['full'])

    def test_diff_error_fallback_is_full(self):
        self.assertTrue(all(r['decision']=='run' for r in plan(force_full=True)['suites'].values()))

    def test_required_skip_failure_cancelled_or_missing_fails_aggregate(self):
        for status in ['skipped','failure','cancelled','missing']:
            result,errors=finish(plan(),results(messaging=status),ENV)
            self.assertTrue(errors)
            self.assertNotEqual(result['suites']['messaging']['status'],'passed')

    def test_static_and_plan_failure_never_hidden(self):
        for job in ['static','plan']:
            self.assertTrue(finish(plan(),results(messaging='success',**{job:'failure'}),ENV)[1])

    def test_missing_unknown_or_invalid_suite_not_pass(self):
        for kind in ['missing','unknown','invalid']:
            p=plan()
            if kind=='missing':del p['suites']['java-pilot']
            elif kind=='unknown':p['suites']['new-course']={'decision':'not-required'}
            else:p['suites']['messaging']['decision']='reuse'
            self.assertTrue(finish(p,results(messaging='success'),ENV)[1])

    def test_docs_scope_is_not_real_pass(self):
        result,errors=finish(plan(changed=['README.md']),results(),ENV)
        self.assertFalse(errors)
        self.assertTrue(all(r['status']=='not-run' for r in result['suites'].values()))

    def test_same_workflow_partial_rerun_does_not_invent_execution_time(self):
        old,_=finish(plan(),results(messaging='success'),ENV)
        new,_=finish(plan(),results(messaging='success'),dict(ENV,GITHUB_RUN_ATTEMPT='2'))
        self.assertEqual(old['suites'],new['suites'])
        self.assertNotIn('executed_at',new['suites']['messaging'])
        self.assertNotIn('source_run_attempt',new['suites']['messaging'])

    def test_real_pass_only_for_selected_actual_success(self):
        result,errors=finish(plan(),results(messaging='success'),ENV)
        self.assertFalse(errors)
        self.assertEqual(result['suites']['messaging']['status'],'passed')
        self.assertEqual(result['suites']['java-pilot']['status'],'not-run')


class GitRangeTests(unittest.TestCase):
    def test_cumulative_diff_never_uses_synchronize_before(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            def git(*args):
                return subprocess.check_output(['git',*args],cwd=root,stderr=subprocess.DEVNULL).decode().strip()
            git('init');git('config','user.name','CI Test');git('config','user.email','ci@example.invalid')
            (root/'README.md').write_text('base');git('add','.');git('commit','-m','base');base=git('rev-parse','HEAD')
            (root/'M.java').write_text('code');git('add','.');git('commit','-m','code');before=git('rev-parse','HEAD')
            (root/'README.md').write_text('docs');git('add','.');git('commit','-m','docs');head=git('rev-parse','HEAD')
            event=copy.deepcopy(EVENT);event['before']=before;event['pull_request']['base']['sha']=base;event['pull_request']['head']['sha']=head
            self.assertEqual(set(event_range('pull_request',event,root)[0]),{'README.md','M.java'})
            git('mv','M.java','N.java');git('commit','-m','rename');event['pull_request']['head']['sha']=git('rev-parse','HEAD')
            self.assertEqual(set(event_range('pull_request',event,root)[0]),{'README.md','N.java'})
            # When a base-tracked file moves, both deleted and added paths remain visible.
            event['pull_request']['base']['sha']=before
            self.assertEqual(set(event_range('pull_request',event,root)[0]),{'README.md','M.java','N.java'})

    def test_main_and_manual_are_full(self):
        for event in ['push','workflow_dispatch','release']:
            self.assertTrue(event_range(event,{},Path('.'))[1])


if __name__=='__main__':unittest.main()
