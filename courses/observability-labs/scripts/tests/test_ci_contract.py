"""Contract checks plus three owned Python process fixtures; never Java or a backend."""
from pathlib import Path
import contextlib,copy,errno,importlib.util,io,json,os,shutil,signal,subprocess,sys,tempfile,time,unittest
from unittest.mock import patch,Mock
S=Path(__file__).resolve().parents[1];sys.path.insert(0,str(S));import verify_ci as ci
class CIContracts(unittest.TestCase):
 def setUp(self):
  variants=json.loads((S.parent/'manifest/variants-extended.json').read_text())
  public=sorted(ci.strict.inventory(S.parent/'observability-lab/src/test/java'))
  self.manifest={'current-main':{'expected_test_cases':public,'expected_failure_cases':[]},**variants}
  self.report={'status':'PASS','selected':list(self.manifest),'results':[]}
  for name,item in self.manifest.items():
   failures=item['expected_failure_cases']
   self.report['results'].append({'variant':name,'status':'PASS','compilation_ok':True,'compile_exit':0,'test_exit':1 if failures else 0,'tests':len(item['expected_test_cases']),'failures':len(failures),'skipped':0,'failed_business_cases':[{'case':c} for c in failures],'run_directory':'validation-runs/MOCK-'+name})
 def rejected(self,change):
  data=copy.deepcopy(self.report);change(data)
  with self.assertRaises(ValueError):ci.validate_report(data,self.manifest)
 def test_exact_fifteen_scenarios_are_accepted(self):self.assertEqual(15,len(ci.validate_report(self.report,self.manifest)))
 def test_missing_scenario_is_rejected(self):self.rejected(lambda d:d['results'].pop())
 def test_duplicate_fresh_directory_is_rejected(self):self.rejected(lambda d:d['results'][1].update(run_directory=d['results'][0]['run_directory']))
 def test_compilation_failure_is_not_business_success(self):self.rejected(lambda d:d['results'][3].update(compile_exit=1,compilation_ok=False))
 def test_extra_business_failure_is_rejected(self):self.rejected(lambda d:d['results'][4]['failed_business_cases'].append({'case':'unknown#method'}))
 def test_missing_business_failure_is_rejected(self):self.rejected(lambda d:d['results'][4]['failed_business_cases'].pop())
 def test_skip_is_rejected(self):self.rejected(lambda d:d['results'][0].update(skipped=1))
 def test_main_subset_is_rejected(self):self.rejected(lambda d:d['results'][0].update(tests=27))
 def test_negative_zero_exit_is_rejected(self):self.rejected(lambda d:d['results'][4].update(test_exit=0))
 def test_correct_nonzero_exit_is_rejected(self):self.rejected(lambda d:d['results'][0].update(test_exit=1))
 def test_stale_overall_pass_cannot_hide_row_failure(self):self.rejected(lambda d:d['results'][0].update(status='BLOCKED'))
 def test_ports_require_all_eight_cleanup_markers_and_refusal(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);p=root/'run/build/test-results/test';p.mkdir(parents=True);xml=p/'TEST-MOCK.xml'
   xml.write_text('\n'.join('C12_PORT_CLEANUP port='+str(30000+n)+' CLOSED' for n in range(8)))
   fake=Mock();fake.__enter__=Mock(return_value=fake);fake.__exit__=Mock(return_value=False);fake.connect_ex.return_value=errno.ECONNREFUSED
   with patch.object(ci,'R',root),patch.object(ci.socket,'socket',return_value=fake):
    self.assertEqual(8,len(ci.closed_ports([{'run_directory':'run'}])))
    fake.connect_ex.return_value=0
    with self.assertRaises(ValueError):ci.closed_ports([{'run_directory':'run'}])
    fake.connect_ex.return_value=errno.ETIMEDOUT
    with self.assertRaises(ValueError):ci.closed_ports([{'run_directory':'run'}])
    xml.write_text('C12_PORT_CLEANUP port=30000 CLOSED')
    with self.assertRaises(ValueError):ci.closed_ports([{'run_directory':'run'}])
 def test_python_optimized_mode_fails_before_git_or_java(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);scripts=root/'scripts';scripts.mkdir()
   for name in ['verify_ci.py','verify_java_variants.py']:shutil.copy2(S/name,scripts/name)
   p=subprocess.run([sys.executable,'-O',str(scripts/'verify_ci.py')],capture_output=True,text=True,timeout=5,env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'})
   self.assertNotEqual(0,p.returncode);receipt=json.loads((root/'evidence/ci/receipt.json').read_text());self.assertEqual('FAIL',receipt['status']);self.assertIn('Python -O',receipt['reason']);self.assertNotIn('lock_sha256_before',receipt)
 def test_early_environment_failure_still_writes_receipt(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp)
   with patch.object(ci,'R',root),patch.object(ci,'source_snapshot',side_effect=ValueError('MOCK source unavailable')),patch.object(ci,'OwnedProcess') as child,patch.object(ci.signal,'signal'):
    self.assertEqual(1,ci.main());child.assert_not_called()
   receipt=json.loads((root/'evidence/ci/receipt.json').read_text());self.assertEqual('FAIL',receipt['status']);self.assertIn('MOCK source unavailable',receipt['reason'])
 def exercise_mocked_main(self,mutate=False,wait_error=None,cleanup_status='PASS'):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);(root/'validation').mkdir();(root/'validation/gradle.lockfile').write_text('MOCK LOCK')
   (root/'manifest').mkdir();shutil.copy2(S.parent/'manifest/variants-extended.json',root/'manifest/variants-extended.json')
   jdk=root/'jdk';(jdk/'bin').mkdir(parents=True);(jdk/'lib').mkdir();(jdk/'bin/javac').touch();(jdk/'lib/ct.sym').touch();(jdk/'release').write_text('JAVA_VERSION="21.0.12.1"\nIMPLEMENTOR="Eclipse Adoptium"\n')
   gradle=root/'gradle';(gradle/'bin').mkdir(parents=True);(gradle/'bin/gradle').touch()
   completed=Mock(returncode=0,stdout='MOCK javac 21.0.12.1 Gradle 8.10.2',stderr='')
   child=Mock();child.wait.return_value=0;child.wait.side_effect=wait_error;child.stop.return_value={'status':cleanup_status,'registered':[],'remaining':[]}
   def launch(command,log):
    Path(command[-1]).write_text(json.dumps(self.report));return child
   before={'MOCK-source':'same'};after={'MOCK-source':'changed' if mutate else 'same'}
   with patch.object(ci,'R',root),patch.dict(os.environ,{'JAVA_HOME':str(jdk),'GRADLE_HOME':str(gradle)}),patch.object(ci,'source_snapshot',side_effect=[before,after]),patch.object(ci.subprocess,'run',return_value=completed),patch.object(ci,'OwnedProcess',side_effect=launch),patch.object(ci.strict,'inventory',return_value=set(self.manifest['current-main']['expected_test_cases'])),patch.object(ci.strict,'read_results'),patch.object(ci,'closed_ports',return_value=[{'MOCK':True}]*8),patch.object(ci.signal,'signal'),contextlib.redirect_stdout(io.StringIO()):
    code=ci.main()
   return code,json.loads((root/'evidence/ci/receipt.json').read_text())
 def test_mocked_full_orchestration_records_exact_totals(self):
  code,receipt=self.exercise_mocked_main();self.assertEqual(0,code);self.assertEqual('PASS',receipt['status']);self.assertEqual(167,receipt['test_executions']);self.assertEqual(52,receipt['expected_business_failures']);self.assertTrue(receipt['source_unchanged'])
 def test_source_mutation_overrides_otherwise_successful_mocked_run(self):
  code,receipt=self.exercise_mocked_main(mutate=True);self.assertEqual(1,code);self.assertEqual('FAIL',receipt['status']);self.assertFalse(receipt['source_unchanged']);self.assertIn('integrity',receipt['reason'])
 def test_timeout_receipt_keeps_failure_and_cleanup_result(self):
  code,receipt=self.exercise_mocked_main(wait_error=subprocess.TimeoutExpired(['MOCK'],.1));self.assertEqual(1,code);self.assertEqual('FAIL',receipt['status']);self.assertIn('TimeoutExpired',receipt['reason']);self.assertEqual('PASS',receipt['process_cleanup']['status'])
 def test_interruption_receipt_keeps_failure_and_cleanup_result(self):
  code,receipt=self.exercise_mocked_main(wait_error=InterruptedError('MOCK interrupted'));self.assertEqual(1,code);self.assertEqual('FAIL',receipt['status']);self.assertIn('InterruptedError',receipt['reason']);self.assertEqual('PASS',receipt['process_cleanup']['status'])
 def test_uncertain_cleanup_cannot_become_success(self):
  code,receipt=self.exercise_mocked_main(cleanup_status='FAIL');self.assertEqual(1,code);self.assertEqual('FAIL',receipt['status']);self.assertIn('cleanup',receipt['reason'])
 def test_changed_birth_is_refused_without_any_signal(self):
  owned=ci.OwnedProcess.__new__(ci.OwnedProcess);owned.owner=123;owned.root={'pid':456,'start_ticks':10};owned.entries={456:{'identity':owned.root,'fd':99}};owned.finished=False;owned.process=Mock(pid=456)
  with patch.object(owned,'capture'),patch.object(owned,'close_handles'),patch.object(ci,'child_pids',return_value=[]),patch.object(ci.select,'select',return_value=([],[],[])),patch.object(ci,'process_identity',return_value={'pid':456,'start_ticks':11}),patch.object(ci.signal,'pidfd_send_signal') as send:
   report=owned.stop(term_seconds=.01,kill_seconds=.01)
  self.assertEqual('FAIL',report['status']);self.assertTrue(any('birth changed' in e for e in report['errors']));send.assert_not_called()
 def owned_python_case(self,mode):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);pidfile=root/'child.pid';logfile=root/'fixture.log'
   child="import os,signal,time; from pathlib import Path; signal.signal(signal.SIGTERM,signal.SIG_IGN); "+("os.setsid(); " if mode=='leader_exited' else '')+"Path("+repr(str(pidfile))+").write_text(str(os.getpid())); time.sleep(60)"
   spawn="subprocess.Popen([sys.executable,'-c',"+repr(child)+"])"
   spawn=spawn if mode=='leader_exited' else 'threading.Thread(target=lambda: '+spawn+').start()'
   leader="import subprocess,sys,time,threading; from pathlib import Path; "+spawn+"; p=Path("+repr(str(pidfile))+");\nwhile not p.exists(): time.sleep(.01)\n"+("sys.exit(0)" if mode=='leader_exited' else "time.sleep(60)")
   with logfile.open('w') as log:
    owned=ci.OwnedProcess([sys.executable,'-c',leader],log)
    try:
     if mode=='leader_exited':self.assertEqual(0,owned.wait(4))
     else:
      end=time.monotonic()+4
      while not pidfile.exists() and time.monotonic()<end:owned.capture();time.sleep(.02)
      self.assertTrue(pidfile.exists());owned.capture()
     child_pid=int(pidfile.read_text());self.assertIsNotNone(ci.process_identity(child_pid))
     report=owned.stop(term_seconds=.2,kill_seconds=1)
     self.assertEqual('PASS',report['status'],report);self.assertEqual([],report['remaining']);self.assertIsNone(ci.process_identity(child_pid));self.assertTrue(any(s['pid']==child_pid and s['signal']=='SIGKILL' for s in report['signals']))
     return report
    finally:
     if not owned.finished:owned.stop(term_seconds=.2,kill_seconds=1)
 def test_actual_python_leader_exits_first_detached_child_is_cleaned(self):self.owned_python_case('leader_exited')
 def test_actual_python_term_exits_leader_ignoring_child_is_killed(self):self.owned_python_case('term_leader')
 def test_actual_python_empty_scope_cleanup_is_safe(self):
  with tempfile.TemporaryFile(mode='w') as log:
   owned=ci.OwnedProcess([sys.executable,'-c','print("fixture done")'],log)
   try:
    self.assertEqual(0,owned.wait(4));report=owned.stop(term_seconds=.2,kill_seconds=1);self.assertEqual('PASS',report['status'],report);self.assertEqual([],report['signals'])
   finally:
    if not owned.finished:owned.stop(term_seconds=.2,kill_seconds=1)
 def query_fixture(self,rc,stdout,stderr):
  query=Mock(pid=999,returncode=rc);query.communicate.return_value=(stdout,stderr)
  return query
 def test_ps_no_match_requires_exact_empty_streams(self):
  with patch.object(ci,'process_identity',return_value={'pid':123}),patch.object(ci.subprocess,'Popen',return_value=self.query_fixture(1,'','')):
   self.assertEqual([],ci.child_pids(123))
 def test_ps_valid_pid_rows_exclude_only_the_query_process(self):
  with patch.object(ci,'process_identity',return_value={'pid':123}),patch.object(ci.subprocess,'Popen',return_value=self.query_fixture(0,'   456\n  999\n  789\n','')):
   self.assertEqual([456,789],ci.child_pids(123))
 def test_ps_rc1_diagnostics_are_not_an_empty_child_set(self):
  with patch.object(ci,'process_identity',return_value={'pid':123}),patch.object(ci.subprocess,'Popen',return_value=self.query_fixture(1,'','ps: error: cannot inspect process table')):
   with self.assertRaisesRegex(ValueError,'diagnostics'):ci.child_pids(123)
 def test_ps_uncertain_exit_streams_and_pid_format_are_rejected(self):
  cases=[(0,'456\n','warning'),(1,'456\n',''),(1,' \n',''),(2,'',''),(0,'',''),(0,'PID\n',''),(0,'0\n',''),(0,'-2\n',''),(0,'12 13\n',''),(0,'12\n12\n',''),(0,'12\n\n',''),(0,'2147483648\n','')]
  for rc,stdout,stderr in cases:
   with self.subTest(rc=rc,stdout=stdout,stderr=stderr),patch.object(ci,'process_identity',return_value={'pid':123}),patch.object(ci.subprocess,'Popen',return_value=self.query_fixture(rc,stdout,stderr)):
    with self.assertRaises(ValueError):ci.child_pids(123)
 def cleanup_query_fixture(self,rc,stdout,stderr):
  owned=ci.OwnedProcess.__new__(ci.OwnedProcess);owned.owner=123;owned.root={'pid':456,'start_ticks':10};owned.entries={};owned.finished=False;owned.process=Mock(pid=456)
  with patch.object(owned,'close_handles'),patch.object(ci,'process_identity',return_value={'pid':123}),patch.object(ci.subprocess,'Popen',return_value=self.query_fixture(rc,stdout,stderr)),patch.object(ci.signal,'pidfd_send_signal') as send:
   result=owned.stop(term_seconds=.01,kill_seconds=.01)
  send.assert_not_called();return result
 def test_full_cleanup_cannot_pass_when_discovery_reports_error(self):
  report=self.cleanup_query_fixture(1,'','ps: error: cannot inspect process table');self.assertEqual('FAIL',report['status']);self.assertTrue(any('diagnostics' in e for e in report['errors']))
 def test_full_cleanup_accepts_confirmed_empty_scope(self):
  report=self.cleanup_query_fixture(1,'','');self.assertEqual('PASS',report['status']);self.assertEqual([],report['errors']);self.assertEqual([],report['remaining'])
if __name__=='__main__':unittest.main()
