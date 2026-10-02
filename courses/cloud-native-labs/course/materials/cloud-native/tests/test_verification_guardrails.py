"""验证器离线回归；subprocess调用均为mock，合成class字节从不交给JVM。"""
import hashlib,importlib.util,json,pathlib,subprocess,tempfile,unittest
from unittest.mock import patch
import docker_variant_verify,variant_verify,docker_verify
from verification_guard import (VerificationSetupError,ContractViolation,claim_evidence,claim_report,
    require_selection,java_source_manifest,class_manifest,verify_compilation)
ROOT=pathlib.Path(__file__).resolve().parents[1]

def module_at(name,path):
    spec=importlib.util.spec_from_file_location(name,path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module

class SelectionTests(unittest.TestCase):
    def test_empty_selection_rejected(self):
        with self.assertRaises(VerificationSetupError):require_selection([],['one'])
    def test_duplicate_selection_rejected(self):
        with self.assertRaises(VerificationSetupError):require_selection(['one','one'],['one'])
    def test_unknown_selection_rejected(self):
        with self.assertRaises(VerificationSetupError):require_selection(['absent'],['one'])
    def test_empty_docker_matrix_never_invokes_runtime(self):
        with tempfile.TemporaryDirectory() as d,patch.object(docker_variant_verify,'PLANS',[]),patch.object(docker_variant_verify,'run_verification') as runtime:
            with self.assertRaises(VerificationSetupError):docker_variant_verify.run_matrix([],{},'',d)
            runtime.assert_not_called()
    def test_empty_java_matrix_never_invokes_compiler(self):
        with tempfile.TemporaryDirectory() as d,patch.object(variant_verify,'VARIANTS',{}),patch('variant_verify.subprocess.run') as run:
            with self.assertRaises(VerificationSetupError):variant_verify.run(pathlib.Path(d)/'result.json')
            run.assert_not_called()
    def test_partial_docker_matrix_cannot_claim_full_matrix_pass(self):
        with tempfile.TemporaryDirectory() as d,patch.object(docker_variant_verify,'PLANS',['wrong-ready']),patch.object(docker_variant_verify,'run_verification') as runtime:
            with self.assertRaises(VerificationSetupError):docker_variant_verify.run_matrix([],{},'',d)
            runtime.assert_not_called()
    def test_partial_policy_matrix_cannot_claim_full_matrix_pass(self):
        with tempfile.TemporaryDirectory() as d,patch.object(variant_verify,'VARIANTS',{'reference-expression':({},True)}),patch('variant_verify.subprocess.run') as run:
            with self.assertRaises(VerificationSetupError):variant_verify.run(pathlib.Path(d)/'result.json')
            run.assert_not_called()
    def test_zero_discovered_offline_tests_is_failure(self):
        verifier=module_at('c11_offline_entry',ROOT/'bin/verify_offline.py')
        with self.assertRaises(VerificationSetupError):verifier.load_suite('no_such_test_*.py')

class EvidenceTests(unittest.TestCase):
    def test_old_pass_report_is_never_reused_or_overwritten(self):
        with tempfile.TemporaryDirectory() as d:
            report=pathlib.Path(d)/'result.json';report.write_text('{"status":"PASS","run_id":"old"}')
            old=report.read_bytes()
            with self.assertRaises(VerificationSetupError):claim_report(report)
            self.assertEqual(report.read_bytes(),old)
    def test_nonempty_evidence_directory_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            (pathlib.Path(d)/'old.log').write_text('old')
            with self.assertRaises(VerificationSetupError):claim_evidence(d)
    def test_new_reports_have_distinct_run_ids(self):
        with tempfile.TemporaryDirectory() as d:
            a=claim_report(pathlib.Path(d)/'a.json');b=claim_report(pathlib.Path(d)/'b.json')
            self.assertNotEqual(a['run_id'],b['run_id'])
            self.assertEqual(json.loads((pathlib.Path(d)/'a.json').read_text())['status'],'RUNNING')

class CompiledArtifactTests(unittest.TestCase):
    def fixture(self,base):
        root=base/'app';classes=base/'classes';(root/'src/labs').mkdir(parents=True);classes.mkdir()
        (root/'src/labs/App.java').write_text('class App {}\n')
        (classes/'App.class').write_bytes(b'synthetic-class-not-executable')
        receipt={'status':'COMPILED','release':21,'sources':java_source_manifest(root),'classes':class_manifest(classes)}
        (classes/'compile-receipt.json').write_text(json.dumps(receipt))
        return root,classes
    def test_missing_receipt_rejects_old_class(self):
        with tempfile.TemporaryDirectory() as d:
            root,classes=self.fixture(pathlib.Path(d));(classes/'compile-receipt.json').unlink()
            with self.assertRaises(VerificationSetupError):verify_compilation(classes,root)
    def test_changed_source_rejects_previous_output(self):
        with tempfile.TemporaryDirectory() as d:
            root,classes=self.fixture(pathlib.Path(d));(root/'src/labs/App.java').write_text('class App { int x; }')
            with self.assertRaises(VerificationSetupError):verify_compilation(classes,root)
    def test_extra_stale_class_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root,classes=self.fixture(pathlib.Path(d));(classes/'Old.class').write_bytes(b'old')
            with self.assertRaises(VerificationSetupError):verify_compilation(classes,root)
    def test_changed_class_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root,classes=self.fixture(pathlib.Path(d));(classes/'App.class').write_bytes(b'changed')
            with self.assertRaises(VerificationSetupError):verify_compilation(classes,root)
    def test_matching_synthetic_receipt_checks_integrity_only(self):
        with tempfile.TemporaryDirectory() as d:
            root,classes=self.fixture(pathlib.Path(d));self.assertEqual(verify_compilation(classes,root)['release'],21)
    def test_compile_refuses_existing_output_before_invoking_javac(self):
        compiler=module_at('c11_compile_entry',ROOT/'bin/compile.py')
        with tempfile.TemporaryDirectory() as d:
            called=[]
            with self.assertRaises(VerificationSetupError):compiler.compile_project(pathlib.Path(d),lambda *a,**k:called.append(a))
            self.assertEqual(called,[])

class NegativeClassificationTests(unittest.TestCase):
    def test_infrastructure_error_never_counts_as_killed_wrong_solution(self):
        for variant in docker_variant_verify.PLANS:
            self.assertFalse(docker_variant_verify.expected_semantic_failure(variant,VerificationSetupError('command failed'),{'cases':['network_redis_1_CONNECT']},[]))
    def test_arbitrary_assertion_never_counts_as_swallowed_term(self):
        report={'cases':['network_redis_1_CONNECT']};commands=[{'stdout':'slow_started','returncode':0,'argv':[]}]
        self.assertFalse(docker_variant_verify.expected_semantic_failure('wrong-shell-term',AssertionError('host was slow'),report,commands))
    def test_wrong_named_contract_is_not_expected_negative(self):
        self.assertFalse(docker_variant_verify.expected_semantic_failure('wrong-ready',ContractViolation('runtime_image_contents',{}),{'cases':[]},[]))
    def test_matching_named_contract_is_accepted(self):
        self.assertTrue(docker_variant_verify.expected_semantic_failure('wrong-shell-term',ContractViolation('sigterm_forced_kill',{'exit_code':137}),{'cases':[]},[]))
    def test_empty_business_result_cannot_make_docker_pass(self):
        def command(argv,**kwargs):return subprocess.CompletedProcess(argv,0,'27.0.0' if 'info' in argv else '','')
        env={'LAB_PROJECT_NAME':'totalacademy-guard-c11-01-verify-abcdef12','CLOUDNATIVE_NAMESPACE':'c11-verify-1234567890abcdef','CLOUDNATIVE_HTTP_PORT':'18085','REDIS_PASSWORD':'synthetic-password-only'}
        with tempfile.TemporaryDirectory() as d,patch('docker_verify.subprocess.run',side_effect=command),patch('docker_verify.wait_status'),patch('docker_verify.fresh_inventory_contract',return_value=[]):
            with self.assertRaises(VerificationSetupError):docker_verify.run_verification(['docker','compose','--project-name','totalacademy-guard-c11-01-verify-abcdef12','-f',str(ROOT.parents[1]/'infra/cloudnative.compose.yaml')],env,'http://127.0.0.1:18085',d)
            self.assertEqual(json.loads((pathlib.Path(d)/'docker-report.json').read_text())['status'],'FAIL')

class ScopeGuardTests(unittest.TestCase):
    def context(self):
        project='totalacademy-guard-c11-01-verify-abcdef12'
        return ['docker','compose','--project-name',project,'-f',str(ROOT.parents[1]/'infra/cloudnative.compose.yaml')],{'LAB_PROJECT_NAME':project,'CLOUDNATIVE_NAMESPACE':'c11-verify-1234567890abcdef','CLOUDNATIVE_HTTP_PORT':'18085'}
    def test_duplicate_project_flag_rejected(self):
        argv,env=self.context();argv+=['--project-name','production']
        with self.assertRaises(docker_verify.InvalidEnvironment):docker_verify.validate_context(argv,env,'http://127.0.0.1:18085')
    def test_image_namespace_mismatch_rejected(self):
        argv,env=self.context();env['LAB_PROJECT_NAME']='other-project'
        with self.assertRaises(docker_verify.InvalidEnvironment):docker_verify.validate_context(argv,env,'http://127.0.0.1:18085')
    def test_destructive_subcommand_cannot_enter_global_options(self):
        argv,env=self.context();argv+=['down','--volumes']
        with self.assertRaises(docker_verify.InvalidEnvironment):docker_verify.validate_context(argv,env,'http://127.0.0.1:18085')
    def test_implicit_compose_file_is_rejected(self):
        argv,env=self.context();argv=argv[:-2]
        with self.assertRaises(docker_verify.InvalidEnvironment):docker_verify.validate_context(argv,env,'http://127.0.0.1:18085')
    def test_override_cannot_publish_redis_or_replace_volume(self):
        argv,env=self.context()
        with tempfile.TemporaryDirectory() as d:
            path=pathlib.Path(d)/'unsafe.json';path.write_text(json.dumps({'services':{'redis':{'ports':['0.0.0.0:6379:6379']}}}))
            argv+=['-f',str(path)]
            with self.assertRaises(docker_verify.InvalidEnvironment):docker_verify.validate_context(argv,env,'http://127.0.0.1:18085')

if __name__=='__main__':unittest.main(verbosity=2)
