import copy,json,os,subprocess,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import legal_preflight as pre

class PreflightTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name);self.output=self.root/'outputs'
        self.context={'event':'push','ref':pre.REF,'phase':'','repository':'weilhuang/backend-interview-labs','run_id':'123','run_attempt':'1','commit':'a'*40,'tree':'b'*40,'checker_sha256':{k:'c'*64 for k in pre.FILES}}
        p=patch.dict(os.environ,{'RUNNER_TEMP':str(self.root),'GITHUB_OUTPUT':str(self.output)},clear=True);p.start();self.addCleanup(p.stop)
    def run_check(self,error=None):
        with patch.object(pre,'source_context',return_value=self.context),patch.object(pre,'verify_legal',side_effect=error,return_value=dict(pre.LEGAL_ID)):
            return pre.main()
    def receipt(self):return json.loads((self.root/'academy-legal-preflight-123-1/legal-preflight.json').read_text())
    def test_success_exact_context_no_course_or_action_claim(self):
        self.assertEqual(self.run_check(),0);value=self.receipt();self.assertEqual(value['status'],pre.PASS);self.assertEqual(value['ui_actions'],0);self.assertEqual(value['course_acceptance'],'NOT_RUN')
        for key,value in self.context.items():self.assertEqual(self.receipt()[key],value)
        self.assertEqual(self.output.read_text(),'collected=true\n')
    def test_typed_failure_receipt_is_uploaded_but_job_fails(self):
        self.assertEqual(self.run_check(subprocess.TimeoutExpired('PRIVATE_COMMAND',15)),1)
        value=self.receipt();self.assertEqual(value['status'],pre.FAIL);self.assertEqual(value['error_code'],'TOTAL_DEADLINE');self.assertNotIn('PRIVATE',json.dumps(value));self.assertTrue(self.output.exists())
    def test_unexpected_error_text_is_never_exported(self):
        self.assertEqual(self.run_check(OSError('PRIVATE_ENVIRONMENT')),1);self.assertEqual(self.receipt()['error_code'],'OTHER_FAILURE');self.assertNotIn('PRIVATE',json.dumps(self.receipt()))
    def test_existing_directory_or_stale_output_cannot_be_reused(self):
        out=self.root/'academy-legal-preflight-123-1';out.mkdir();(out/'legal-preflight.json').write_text('OLD')
        with self.assertRaises(FileExistsError):self.run_check()
        self.assertFalse(self.output.exists());self.assertEqual((out/'legal-preflight.json').read_text(),'OLD')
    def test_cancellation_does_not_mark_collected(self):
        with self.assertRaises(InterruptedError):self.run_check(InterruptedError())
        self.assertFalse(self.output.exists());self.assertFalse((self.root/'academy-legal-preflight-123-1/legal-preflight.json').exists())
    def test_collection_failure_never_marks_upload_ready(self):
        with patch.object(pre,'publish',side_effect=OSError('fixture')),self.assertRaises(OSError):self.run_check()
        self.assertFalse(self.output.exists())
    def test_receipt_rejects_unknown_fields_nested_payload_bool_and_false_green(self):
        self.run_check();good=self.receipt()
        for key,value in [('schema',True),('ui_actions',False),('elapsed_seconds',True),('elapsed_seconds',float('nan')),('error_code','OTHER_FAILURE'),('legal_identity',{'environment':{'TOKEN':'PRIVATE'}}),('checker_sha256',{'unknown':'c'*64})]:
            with self.subTest(key=key),self.assertRaises(ValueError):pre.validate({**good,key:value})
        with self.assertRaises(ValueError):pre.validate({**good,'environment':{'PRIVATE':'X'}})
    def test_wrong_source_commit_is_refused_before_network(self):
        repo=Path(pre.__file__).resolve().parents[2]
        env={'GITHUB_EVENT_NAME':'push','GITHUB_REF':pre.REF,'PREFLIGHT_PHASE':'','GITHUB_WORKSPACE':str(repo),'GITHUB_REPOSITORY':'weilhuang/backend-interview-labs','GITHUB_SHA':'a'*40,'GITHUB_RUN_ID':'123','GITHUB_RUN_ATTEMPT':'1'}
        result=subprocess.CompletedProcess([],0,stdout=('b'*40+'\n').encode())
        with patch.dict(os.environ,env),patch.object(pre.subprocess,'run',return_value=result),self.assertRaises(ValueError):pre.source_context()
    def test_other_events_refs_or_phases_are_rejected_even_before_git(self):
        repo=Path(pre.__file__).resolve().parents[2]
        for event,ref,phase in [('push','refs/heads/main',''),('pull_request',pre.REF,''),('workflow_dispatch',pre.REF,'full-validation'),('workflow_dispatch','refs/heads/other','legal-preflight'),('push',pre.REF,'full-validation')]:
            env={'GITHUB_WORKSPACE':str(repo),'GITHUB_REPOSITORY':'weilhuang/backend-interview-labs','GITHUB_EVENT_NAME':event,'GITHUB_REF':ref,'PREFLIGHT_PHASE':phase}
            with patch.dict(os.environ,env),patch.object(pre.subprocess,'run') as git,self.assertRaises(ValueError):pre.source_context()
            git.assert_not_called()
    def test_exact_git_context_and_current_checker_hashes(self):
        repo=Path(pre.__file__).resolve().parents[2]
        env={'GITHUB_EVENT_NAME':'push','GITHUB_REF':pre.REF,'PREFLIGHT_PHASE':'','GITHUB_WORKSPACE':str(repo),'GITHUB_REPOSITORY':'weilhuang/backend-interview-labs','GITHUB_SHA':'a'*40,'GITHUB_RUN_ID':'123','GITHUB_RUN_ATTEMPT':'1'}
        results=[subprocess.CompletedProcess([],0,stdout=(x*40+'\n').encode()) for x in ('a','b')]
        with patch.dict(os.environ,env),patch.object(pre.subprocess,'run',side_effect=results):value=pre.source_context()
        self.assertEqual(value['commit'],'a'*40);self.assertEqual(value['tree'],'b'*40);self.assertEqual(set(value['checker_sha256']),set(pre.FILES))
    def test_preflight_is_exact_ref_only_and_skips_native_package(self):
        import yaml
        repo=Path(pre.__file__).resolve().parents[2];doc=yaml.safe_load((repo/'.github/workflows/academy-official.yml').read_text());job=doc['jobs']['legal-preflight']
        self.assertEqual(job['if'],"github.ref == 'refs/heads/academy-validation/legal-preflight' && (github.event_name == 'push' || (github.event_name == 'workflow_dispatch' && inputs.phase == 'legal-preflight'))")
        self.assertEqual(doc['jobs']['package']['if'],"(github.event_name == 'push' && (github.ref == 'refs/heads/academy-validation/smoke' || github.ref == 'refs/heads/academy-validation/full')) || (github.event_name == 'workflow_dispatch' && github.ref != 'refs/heads/academy-validation/legal-preflight' && (inputs.phase == 'export-import-smoke' || inputs.phase == 'full-validation'))")
        self.assertEqual(job['runs-on'],'ubuntu-24.04');self.assertEqual(job['permissions'],{'contents':'read'});self.assertEqual(job['timeout-minutes'],4)
        self.assertEqual(len(job['steps']),4);self.assertEqual(job['steps'][0]['with']['ref'],'${{ github.sha }}')
        self.assertEqual(job['steps'][2]['run'],'python scripts/academy/legal_preflight.py')
        upload=job['steps'][3];self.assertIn("steps.legal_check.outputs.collected == 'true'",upload['if']);self.assertTrue(upload['with']['path'].endswith('/legal-preflight.json'));self.assertNotIn('*',upload['with']['path'])
        serialized=json.dumps(job).lower()
        for forbidden in ('setup-java','docker','gh_token','secrets.','install_toolchain','sudo','jvm','xvfb'):
            self.assertNotIn(forbidden,serialized)

if __name__=='__main__':unittest.main()
