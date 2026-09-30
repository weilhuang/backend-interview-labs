from pathlib import Path
import sys
import unittest
import yaml
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from plan import SUITES, REAL_JOBS

ROOT = Path(__file__).resolve().parents[3]


class WorkflowContractTests(unittest.TestCase):
    def workflow(self, name):
        return yaml.load((ROOT/'.github/workflows'/f'{name}.yml').read_text(), Loader=yaml.BaseLoader)

    def test_one_owner_no_paths_no_schedule_and_full_entrypoints(self):
        workflow = self.workflow('ci')
        self.assertEqual(set(workflow['on']), {'pull_request','push','workflow_dispatch','release'})
        self.assertIn('labeled',workflow['on']['pull_request']['types'])
        self.assertIn('edited',workflow['on']['pull_request']['types'])
        self.assertNotIn('paths',workflow['on']['pull_request'])
        self.assertEqual(workflow['concurrency']['cancel-in-progress'],"${{ github.event_name == 'pull_request' }}")
        self.assertIn('github.run_id',workflow['concurrency']['group'])
        self.assertIn('github.event_name',workflow['concurrency']['group'])
        self.assertEqual(workflow['permissions'], {'contents':'read'})
        self.assertNotIn('permissions',workflow['jobs']['plan'])
        self.assertNotIn('GH_TOKEN',str(workflow))
        self.assertNotIn('secrets',str(workflow))
        self.assertEqual(set(workflow['jobs']['result']['needs']), set(SUITES)|{'plan','static'})
        self.assertEqual(workflow['jobs']['result']['if'],'always()')
        for suite in SUITES:
            job=workflow['jobs'][suite]
            self.assertEqual(job['uses'],f'./.github/workflows/{suite}.yml')
            self.assertEqual(job['needs'],['plan','static'])
            self.assertNotIn('secrets',job)

    def test_real_jobs_have_stable_names_finite_timeouts_no_nested_concurrency(self):
        for suite in SUITES:
            workflow=self.workflow(suite)
            self.assertEqual(set(workflow['on']),{'workflow_call'})
            self.assertNotIn('concurrency',workflow)
            self.assertEqual(workflow['permissions'],{'contents':'read'})
            names=[]
            for job in workflow['jobs'].values():
                self.assertLessEqual(int(job['timeout-minutes']),60)
                self.assertNotIn('continue-on-error',job)
                if 'matrix.course' in job['name']:
                    names.extend(job['name'].replace('${{ matrix.course }}',x) for x in job['strategy']['matrix']['course'])
                else:
                    names.append(job['name'])
                for step in job['steps']:
                    self.assertNotIn('continue-on-error',step)
                    if step.get('uses')=='actions/checkout@v4':
                        self.assertEqual(step['with']['persist-credentials'],'false')
                    if step.get('uses')=='actions/upload-artifact@v4':
                        self.assertEqual(step['if'],'always()')
                        self.assertEqual(step['with']['retention-days'],'7')
                        self.assertIn('github.run_id',step['with']['name'])
                        self.assertIn('github.run_attempt',step['with']['name'])
                        self.assertEqual(step['with']['if-no-files-found'],'error')
            self.assertEqual(set(names),set(REAL_JOBS[suite]))

    def test_cache_only_downloads_never_reports_outputs_or_local_build_cache(self):
        for suite in SUITES:
            for job in self.workflow(suite)['jobs'].values():
                for step in job['steps']:
                    if step.get('uses')=='actions/cache@v4':
                        paths=step['with']['path'].splitlines()
                        self.assertTrue(all(p.endswith('/caches/modules-2') or p.endswith('/wrapper') for p in paths))
                        self.assertIn('gradle-wrapper.properties',step['with']['key'])
                        self.assertIn('gradle.lockfile',step['with']['key'])

    def test_every_course_has_one_layer_appropriate_three_phase_gate(self):
        expected={
            'java-pilot': {'check': 'contract'}, 'java-foundations': {'check': 'contract'},
            'java-advanced': {'check': 'contract'}, 'java-frameworks': {'verify': 'contract'},
            'data-storage': {'mysql': 'integration', 'redis': 'integration'},
            'messaging': {'verify': 'contract'}, 'distributed': {'verify': 'contract'},
            'backend-capstone': {'verify': 'contract'}, 'lab-environment': {},
        }
        expanded_courses=[]
        for suite in SUITES:
            for key,job in self.workflow(suite)['jobs'].items():
                steps=[step for step in job['steps'] if 'academy_gate.py roundtrip' in step.get('run','')]
                if key not in expected[suite]:
                    self.assertEqual(steps,[],(suite,key))
                    continue
                self.assertEqual(len(steps),1,(suite,key))
                step=steps[0]
                self.assertIn('--suite '+expected[suite][key],step['run'])
                self.assertIn('--timeout 600',step['run'])
                self.assertEqual(step['timeout-minutes'],'35')
                self.assertEqual(step['working-directory'],'${{ github.workspace }}')
                self.assertNotIn('continue-on-error',step)
                if suite=='data-storage':
                    self.assertEqual(job['timeout-minutes'],'60')
                course=step['env']['ACADEMY_COURSE']
                expanded_courses.extend(job['strategy']['matrix']['course'] if course=='${{ matrix.course }}' else [course])
        from plan import COURSE_ROOTS
        self.assertEqual(set(expanded_courses),COURSE_ROOTS)
        self.assertEqual(len(expanded_courses),len(COURSE_ROOTS))

    def test_job_budget_covers_gate_old_real_duration_and_upload_margin(self):
        # Observed successful jobs at 1fb27d8, seconds; advanced matrix uses its maximum.
        old_seconds={'java-pilot': {'check':90}, 'java-foundations': {'check':233},
                     'java-advanced': {'check':180}, 'java-frameworks': {'verify':311},
                     'data-storage': {'mysql':183,'redis':176}, 'messaging': {'verify':888},
                     'distributed': {'verify':470}, 'backend-capstone': {'verify':538}}
        for suite,jobs in old_seconds.items():
            for key,seconds in jobs.items():
                job=self.workflow(suite)['jobs'][key]
                gate=next(s for s in job['steps'] if 'academy_gate.py roundtrip' in s.get('run',''))
                self.assertGreater(int(job['timeout-minutes']),int(gate['timeout-minutes']))
                self.assertGreaterEqual(int(job['timeout-minutes'])*60,seconds+35*60+120)
                self.assertLessEqual(int(job['timeout-minutes']),60)

    def test_three_phase_evidence_is_always_preserved_without_entire_fixture(self):
        for suite in SUITES:
            for job in self.workflow(suite)['jobs'].values():
                if not any('academy_gate.py roundtrip' in step.get('run','') for step in job['steps']):
                    continue
                uploads=[step for step in job['steps'] if step.get('uses')=='actions/upload-artifact@v4']
                self.assertEqual(len(uploads),1)
                artifact=uploads[0]
                self.assertEqual(artifact['if'],'always()')
                paths=artifact['with']['path']
                self.assertIn('-roundtrip.json',paths)
                self.assertIn('source-manifest.json',paths)
                self.assertIn('**/*.log',paths)
                self.assertIn('**/build/test-results/',paths)
                self.assertNotIn('source-fixture.zip',paths)

    def test_static_checks_have_jdk_and_do_not_run_docker(self):
        steps=self.workflow('ci')['jobs']['static']['steps']
        self.assertTrue(any(s.get('uses')=='actions/setup-java@v4' and s['with']['java-version']=='21' for s in steps))
        commands='\n'.join(s.get('run','') for s in steps)
        self.assertNotIn('docker run',commands)
        self.assertIn('academy_gate.py metadata',commands)
        self.assertIn('academy_gate.py legacy-metadata',commands)
        self.assertIn('plan.py --check-inventory',commands)
        self.assertIn('validate_docs.py',commands)


if __name__=='__main__':
    unittest.main()
