"""仅源码静态检查，不启动Java。"""
from pathlib import Path
import ast,json,re,unittest
ROOT=Path(__file__).resolve().parents[1];TASK=ROOT/'identity/01-policy/lab';APP=ROOT/'materials/identity/identity-lab'
class SourceContracts(unittest.TestCase):
    def test_fixed_contract_matches_all_public_java_methods(self):
        contract=json.loads((ROOT/'gate-contract.json').read_text())
        for group,source_root in [('unit',TASK/'test'),('http',APP/'src/test/java')]:
            for suite,expected in contract[group].items():
                text=(source_root/(suite.replace('.','/')+'.java')).read_text()
                actual=re.findall(r'@Test\s+void\s+(\w+)\s*\(',text)
                self.assertEqual(sorted(actual),sorted(expected),suite)
        self.assertEqual(contract['counts'],{'unit_methods':11,'unit_matrix_inner_cases':144,'http_methods':4})
    def test_public_policy_protects_reason_missing_inputs_and_precedence(self):
        s=(TASK/'test/labs/identity/PolicyTest.java').read_text()
        for token in ['new Policy.Decision(allowed,reason)','invalidSubjectId','invalidResourceId','invalidSubjectTenant','invalidResourceTenant','denialPrecedence','fixedDecisionReasons','assertEquals(144,count']:
            self.assertIn(token,s)
        for name in ['wrong-reasons','empty-identifiers','wrong-precedence']:
            self.assertTrue((TASK/f'mutants/{name}/Policy.java').exists())
    def test_one_policy_source_and_answers_not_compiled(self):
        self.assertFalse((APP/'src/main/java/labs/identity/Policy.java').exists())
        self.assertNotIn('authorizeExplicit',(TASK/'src/labs/identity/Policy.java').read_text())
        b=(ROOT/'build.gradle').read_text()
        self.assertIn("main.java.setSrcDirs(['src'])",b)
        self.assertIn('implementation learnerPolicyArtifact',b)
        self.assertNotIn("setSrcDirs(['reference",b)
    def test_receipts_bind_run_sources_tools_and_force_fresh_execution(self):
        s=(ROOT/'scripts/gate_receipts.gradle').read_text()
        for x in ['verifySources()','run_id','binding_sha256','source_sha256','config_sha256','locks_sha256',
            "outputs.upToDateWhen { false }","outputs.cacheIf { false }","afterTest","afterSuite","gradle.taskGraph.afterTask"]:
            self.assertIn(x,s)
        g=(ROOT/'scripts/verify_finalizedby_gate.py').read_text()
        for x in ['--no-build-cache','--rerun-tasks','BUILD_TASKS','fixed shared lock set missing','input changed during execution']:
            self.assertIn(x,g)
        self.assertNotIn("cmd.append('--write-locks')",g)
    def test_finalizer_and_unique_negative_assertion_are_explicit(self):
        self.assertIn("finalizedBy service.tasks.named('httpAcceptance')",(ROOT/'build.gradle').read_text())
        s=(APP/'src/test/java/labs/identity/IdentityNetworkTest.java').read_text()
        self.assertIn('assertEquals(200,own.getStatusCode().value(),"C15_HTTP_OWN_ORDER_200")',s)
        self.assertIn('recordHttpObservation(own.getStatusCode().value())',s)
        self.assertIn('"expected",200,"observed",observed',s)
    def test_task_metadata_is_complete_visible_and_utf16_exact(self):
        meta=json.loads((TASK/'task-info.yaml').read_text())
        expected={str(p.relative_to(TASK)) for p in TASK.rglob('*') if p.is_file() and p.name!='task-info.yaml'}
        self.assertEqual({r['name'] for r in meta['files']},expected)
        self.assertTrue(all(r['visible'] for r in meta['files']))
        row=next(r for r in meta['files'] if 'placeholders' in r);p=row['placeholders'][0]
        data=(TASK/row['name']).read_text().encode('utf-16-le')
        self.assertEqual(data[2*p['offset']:2*(p['offset']+p['length'])].decode('utf-16-le'),p['placeholder_text'])
    def test_student_markdown_has_no_old_status_or_internal_paths(self):
        for p in ROOT.rglob('*.md'):
            s=p.read_text()
            for bad in ['165','R0','R1','恢复','source-freeze','evidence/','scripts/gradle.sh','/workspace/','/tmp/','owner']:
                self.assertNotIn(bad,s,str(p))
    def test_local_markdown_links_resolve(self):
        for p in ROOT.rglob('*.md'):
            for link in re.findall(r'\]\(([^)]+)\)',p.read_text()):
                if not link.startswith(('http://','https://','#')):
                    self.assertTrue((p.parent/link.split('#')[0]).is_file(),(p,link))
    def test_python_sources_parse_and_audit_is_external(self):
        for p in [*ROOT.glob('scripts/*.py'),*ROOT.glob('tests/*.py')]:ast.parse(p.read_text(),filename=str(p))
        self.assertFalse((ROOT/'PROPOSAL_MANIFEST.json').exists())
        self.assertFalse((ROOT/'proposal-evidence').exists())
        self.assertIn('**/__pycache__/',(ROOT/'.gitignore').read_text())
if __name__=='__main__':unittest.main(verbosity=2)
