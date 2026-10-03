"""Typed fixture evidence and workflow gate; never starts an X server locally."""
import copy,json,sys,tempfile,unittest,os
from unittest.mock import patch
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import modal_fixture as fixture
from display_diagnostic import encode

class FixtureEvidence(unittest.TestCase):
    def report(self):
        return {'schema':1,'status':'PASS','kind':'PRIVATE_SYNTHETIC_X11_NOT_IDE_OR_ACCEPTANCE','cases':[{'case':name,'status':'PASS' if i in (0,4) else 'REJECTED'} for i,name in enumerate(fixture.CASE_NAMES)],'cleanup':'REAPED','error':None,'run_id':'123','run_attempt':'1','tested_sha':'a'*40,'elapsed_milliseconds':100}
    def test_exact_success_requires_all_cases_and_cleanup(self):
        value=self.report();self.assertEqual(fixture.report_document(value),value)
        for changes in ({'cases':value['cases'][:-1]},{'cleanup':'UNVERIFIED'},{'error':'CANCELLED'},{'elapsed_milliseconds':True},{'run_id':{'private':'payload'}},{'schema':True},{'status':'RUNNING'},{'environment':{'secret':'PRIVATE'}}):
            with self.assertRaises(ValueError):fixture.report_document({**value,**changes})
    def test_explicit_startup_failure_has_no_false_window_proof(self):
        value={**self.report(),'status':'FAIL','cases':[],'error':'XVFB_START_UNAVAILABLE'}
        self.assertEqual(fixture.report_document(value)['cases'],[])
    def test_partial_case_sequence_cannot_skip_or_relabel(self):
        value=self.report()
        for cases in (list(reversed(value['cases'])),value['cases']*2,[{'case':'PRIVATE_NAME','status':'PASS'}],[{'case':fixture.CASE_NAMES[0],'status':'REJECTED'}]):
            with self.assertRaises(ValueError):fixture.report_document({**value,'cases':cases})
    def test_collector_strict_projection_rejects_nested_private_values(self):
        from collect_evidence import collect
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);run=root/'run';(run/'evidence').mkdir(parents=True);bootstrap=root/'bootstrap';bootstrap.mkdir()
            (bootstrap/fixture.NAME).write_bytes(encode({**self.report(),'error':{'command':'PRIVATE_FIXTURE'}}))
            output=root/'out';collect(run,output,bootstrap=bootstrap)
            self.assertFalse((output/fixture.NAME).exists())
            self.assertNotIn(b'PRIVATE_FIXTURE',(output/'collection.json').read_bytes())
    def test_current_run_source_bound_report_collected_and_replay_omitted(self):
        from collect_evidence import collect
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);run=root/'run';(run/'evidence').mkdir(parents=True);bootstrap=root/'bootstrap';bootstrap.mkdir()
            (bootstrap/fixture.NAME).write_bytes(encode(self.report()))
            with patch.dict(os.environ,{'GITHUB_RUN_ID':'123','GITHUB_RUN_ATTEMPT':'1','GITHUB_SHA':'a'*40}):
                collect(run,root/'good',bootstrap=bootstrap)
                self.assertEqual(json.loads((root/'good'/fixture.NAME).read_text())['status'],'PASS')
            with patch.dict(os.environ,{'GITHUB_RUN_ID':'123','GITHUB_RUN_ATTEMPT':'2','GITHUB_SHA':'a'*40}):
                collect(run,root/'stale',bootstrap=bootstrap)
                self.assertFalse((root/'stale'/fixture.NAME).exists())

    def test_preflight_precedes_ide_only_for_current_full_mode(self):
        import yaml
        repo=Path(fixture.__file__).parents[2];steps=yaml.safe_load((repo/'.github/workflows/academy-official.yml').read_text())['jobs']['package']['steps']
        at=next(i for i,s in enumerate(steps) if 'modal_fixture.py' in s.get('run',''))
        step=steps[at];self.assertEqual(step['timeout-minutes'],1);self.assertNotIn('continue-on-error',step)
        self.assertIn("inputs.phase == 'full-validation'",step['run']);self.assertIn("refs/heads/academy-validation/full",step['run'])
        self.assertLess(at,next(i for i,s in enumerate(steps) if 'install_toolchain.sh "$TOOLCHAIN_DIR"' in s.get('run','')))
        self.assertNotIn('sudo',step['run']);self.assertNotIn('DISPLAY=',step['run'])
if __name__=='__main__':unittest.main()
