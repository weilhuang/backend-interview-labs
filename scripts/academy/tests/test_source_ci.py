import io,json,os,sys,tempfile,unittest,zipfile
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import check_source_ci as source
from gates import GateError,sha

def aggregate():return {'schema_version':1,'repository':source.REPOSITORY,'run_id':10,'run_attempt':1,'head_sha':'head','tested_sha':'merge','full':False,'errors':[],'suites':{'s':{'status':'passed'}}}

def archive(evidence):
    out=io.BytesIO()
    with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:z.writestr('evidence.json',json.dumps(evidence))
    data=out.getvalue();return data,{'digest':'sha256:'+sha(data),'size_in_bytes':len(data)}

class SourceProofTests(unittest.TestCase):
    def test_head_sha_is_not_tested_sha(self):
        source.validate_source_evidence(aggregate(),{'id':10,'run_attempt':1,'head_sha':'head'},'merge',{'s'})
    def test_same_head_different_checkout_rejected(self):
        with self.assertRaises(GateError):source.validate_source_evidence(aggregate(),{'id':10,'run_attempt':1,'head_sha':'head'},'head',{'s'})
    def test_false_full_flag_does_not_invalidate_complete_evidence(self):
        e=aggregate();self.assertFalse(e['full']);source.validate_source_evidence(e,{'id':10,'head_sha':'head'},'merge',{'s'})
    def test_failed_suite_and_errors_rejected(self):
        e=aggregate();e['suites']['s']['status']='skipped'
        with self.assertRaises(GateError):source.validate_source_evidence(e,{'id':10,'head_sha':'head'},'merge',{'s'})
        e=aggregate();e['errors']=['failed']
        with self.assertRaises(GateError):source.validate_source_evidence(e,{'id':10,'head_sha':'head'},'merge',{'s'})
    def test_run_attempt_mismatch_rejected(self):
        with self.assertRaises(GateError):source.validate_source_evidence(aggregate(),{'id':10,'run_attempt':2,'head_sha':'head'},'merge',{'s'})
    def test_artifact_digest_and_single_file_contract(self):
        data,meta=archive(aggregate());self.assertEqual(source.parse_evidence_archive(data,meta),aggregate())
        meta['digest']='sha256:'+'0'*64
        with self.assertRaises(GateError):source.parse_evidence_archive(data,meta)
    def test_traversal_member_rejected_without_extract(self):
        out=io.BytesIO()
        with zipfile.ZipFile(out,'w') as z:z.writestr('../evidence.json','{}')
        data=out.getvalue()
        with self.assertRaises(GateError):source.parse_evidence_archive(data,{'digest':'sha256:'+sha(data),'size_in_bytes':len(data)})
    def test_skipped_job_rejected(self):
        with self.assertRaises(GateError):source.verify_jobs({'total_count':1,'jobs':[{'name':'job','status':'completed','conclusion':'skipped'}]},{'job'})
    def test_duplicate_job_rejected(self):
        row={'name':'job','status':'completed','conclusion':'success'}
        with self.assertRaises(GateError):source.verify_jobs({'total_count':2,'jobs':[row,row]},{'job'})
    def run_gate(self,mutator=None):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'scripts/ci').mkdir(parents=True);(root/'scripts/ci/plan.py').write_text("SUITES={'s': []}\nREAL_JOBS={'s':['real']}\n")
            run={'id':10,'run_number':1,'run_attempt':1,'head_sha':'head','path':'.github/workflows/ci.yml','event':'pull_request','status':'completed','conclusion':'success','html_url':'https://github.com/x'}
            data,artifact=archive(aggregate());artifact.update(id=20,name='ci-evidence-10-1',expired=False,workflow_run={'id':10})
            responses={'git/commits/merge':{'sha':'merge','tree':{'sha':'tree'},'parents':[{'sha':'base'},{'sha':'head'}]},
                'git/ref/heads/academy-validation/smoke':{'object':{'sha':'merge'}},
                'actions/workflows/ci.yml/runs?per_page=20':{'workflow_runs':[run]},
                'actions/runs/10/artifacts?per_page=100':{'total_count':1,'artifacts':[artifact]},'actions/artifacts/20/zip':data,
                'actions/runs/10/jobs?filter=latest&per_page=100':{'total_count':4,'jobs':[{'name':n,'status':'completed','conclusion':'success'} for n in ['real','PR累计验收范围','文档元数据与门禁自测','CI验收总门禁']]}}
            if mutator:mutator(responses)
            env={'GITHUB_REPOSITORY':source.REPOSITORY,'GITHUB_SHA':'merge','GITHUB_REF':source.SMOKE_REF,'GITHUB_EVENT_NAME':'push','GITHUB_API_URL':'https://api.github.com'}
            def git(args,**kw):return 'merge\n' if args[1]=='rev-parse' else 'tree tree\nparent base\nparent head\n\nmessage\n'
            with patch.dict(os.environ,env),patch.object(source,'api',lambda path,raw=False:responses[path]),patch.object(source.subprocess,'check_output',git):return source.check(root)
    def test_full_exact_merge_bootstrap(self):
        result=self.run_gate();self.assertEqual(result['tested_sha'],'merge');self.assertEqual(result['api_head_sha'],'head')
    def test_changed_ref_rejected(self):
        with self.assertRaises(GateError):self.run_gate(lambda r:r['git/ref/heads/academy-validation/smoke']['object'].update(sha='different'))
    def test_remote_tree_mismatch_rejected(self):
        with self.assertRaises(GateError):self.run_gate(lambda r:r['git/commits/merge']['tree'].update(sha='different'))
    def test_incomplete_newer_candidate_blocks(self):
        with self.assertRaises(GateError):self.run_gate(lambda r:r['actions/workflows/ci.yml/runs?per_page=20']['workflow_runs'][0].update(status='in_progress',conclusion=None))
    def test_failed_matching_run_blocks(self):
        with self.assertRaises(GateError):self.run_gate(lambda r:r['actions/workflows/ci.yml/runs?per_page=20']['workflow_runs'][0].update(conclusion='failure'))

if __name__=='__main__':unittest.main()
