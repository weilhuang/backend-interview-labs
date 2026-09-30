from pathlib import Path
import copy
import json
import subprocess
import tempfile
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
                # Distributed adds one shared 900-second sequence, not a budget per mutation.
                extra = 900 if suite == 'distributed' else 0
                self.assertGreaterEqual(int(job['timeout-minutes'])*60,seconds+35*60+extra+120)
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

    def test_distributed_region_gate_executes_and_retains_real_evidence(self):
        job = self.workflow('distributed')['jobs']['verify']
        self.assertEqual(job['timeout-minutes'], '60')
        steps = job['steps']
        commands = [step.get('run', '') for step in steps]
        self.assertIn('./gradlew --no-daemon --no-build-cache --max-workers=1 integrationTest --continue --console=plain -PdockerApiVersion=1.44', commands)
        self.assertTrue(any('academy_gate.py roundtrip' in command and '--suite contract' in command for command in commands))
        gates = [step for step in steps if 'distributed_integration_audit.py' in step.get('run', '')]
        self.assertEqual(len(gates), 1)
        gate = gates[0]
        self.assertEqual(gate['working-directory'], '${{ github.workspace }}')
        self.assertEqual(gate['timeout-minutes'], '16')
        self.assertEqual(gate['env']['ORG_GRADLE_PROJECT_dockerApiVersion'], '1.44')
        for token in ('--execute', '--xa-commit-controls', '--timeout 300', '--total-timeout 900'):
            self.assertIn(token, gate['run'])
        self.assertNotIn('continue-on-error', gate)
        artifact = next(step for step in steps if step.get('uses') == 'actions/upload-artifact@v4')
        self.assertEqual(artifact['if'], 'always()')
        for path in ('build/quality/distributed-region-audit.json',
                     'build/quality/distributed-region-audit/**/source-manifest.json',
                     'build/quality/distributed-region-audit/**/*.log',
                     'build/quality/distributed-region-audit/**/build/test-results/'):
            self.assertIn(path, artifact['with']['path'].splitlines())
        self.assertNotIn('build/quality/distributed-region-audit/', artifact['with']['path'].splitlines())

    def test_distributed_runtime_assertion_rejects_preparation_partial_and_wrong_scope(self):
        step = next(step for step in self.workflow('distributed')['jobs']['verify']['steps']
                    if 'distributed_integration_audit.py' in step.get('run', ''))
        # Execute the actual workflow assertion against JSON fixtures; never invoke Java/Docker.
        assertion = step['run'].split("python - <<'PY'\n", 1)[1].rsplit('\nPY', 1)[0]
        good = {'status': 'PASS', 'docker_integration': 'PASS',
                'runtime': {'status': 'PASS', 'execution_requested': True, 'completed_runs': 8, 'planned_runs': 8},
                'limits': {'gradle_process_seconds': 300, 'total_execution_seconds': 900},
                'reference_runs': [{'module': module, 'status': 'PASS'} for module in ('06-transactions', '07-outbox-cache')],
                'mutation_runs': [{'region': region, 'status': 'PASS'} for region in ('DS-17', 'DS-19', 'DS-21', 'DS-22')],
                'semantic_control_runs': [{'region': region, 'status': 'PASS'} for region in ('DS-17-omit-ra-commit', 'DS-17-omit-rb-commit')]}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'build/quality/distributed-region-audit.json'
            path.parent.mkdir(parents=True)
            def accepted(report):
                path.write_text(json.dumps(report))
                return subprocess.run([sys.executable, '-c', assertion], cwd=directory,
                                      capture_output=True, text=True, timeout=10).returncode == 0
            self.assertTrue(accepted(good))
            bad = copy.deepcopy(good); bad['status'] = bad['docker_integration'] = bad['runtime']['status'] = 'NOT_RUN'
            self.assertFalse(accepted(bad))
            for key, value in (('execution_requested', False), ('execution_requested', 'true'),
                               ('status', 'NOT_RUN'), ('completed_runs', 7), ('planned_runs', 6)):
                bad = copy.deepcopy(good); bad['runtime'][key] = value
                self.assertFalse(accepted(bad), key)
            for section in ('reference_runs', 'mutation_runs', 'semantic_control_runs'):
                bad = copy.deepcopy(good); bad[section].pop()
                self.assertFalse(accepted(bad), section)
                bad = copy.deepcopy(good); bad[section][-1] = bad[section][0]
                self.assertFalse(accepted(bad), section)
                bad = copy.deepcopy(good); bad[section][0]['status'] = 'FAIL'
                self.assertFalse(accepted(bad), section)
            bad = copy.deepcopy(good); bad['limits']['total_execution_seconds'] = 1800
            self.assertFalse(accepted(bad))
            self.assertFalse(accepted({'status': 'PASS'}))

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
