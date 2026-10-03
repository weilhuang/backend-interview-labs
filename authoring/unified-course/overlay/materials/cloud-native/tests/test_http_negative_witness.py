"""HTTP→业务契约→Docker报告→错误解矩阵整路径回归；所有Docker进程与HTTP传输均为mock。

两个HTTP错误解走真实验证器控制流。其他矩阵成员仅是此隔离测试的占位控制，不能当成运行证据。
"""
import copy,http.client,io,json,pathlib,subprocess,tempfile,unittest,urllib.error,urllib.parse
from unittest.mock import patch
import contract,docker_verify,docker_variant_verify
from verification_guard import ContractViolation,VerificationInfrastructureError

ROOT=pathlib.Path(__file__).resolve().parents[1]

class HttpNegativeWitnessTests(unittest.TestCase):
    def exercise(self,target='wrong-ready',event='target',response=None):
        """调用真实run_matrix及两个HTTP变体的run_verification；返回当前临时报告，不运行Docker。"""
        project='totalacademy-witness-c11-verify-abcdef12'
        argv=['docker','compose','--project-name',project,'-f',str(ROOT.parents[1]/'infra/cloudnative.compose.yaml')]
        env={'LAB_PROJECT_NAME':project,'CLOUDNATIVE_NAMESPACE':'c11-verify-0123456789abcdef','CLOUDNATIVE_HTTP_PORT':'18085'}
        original=docker_verify.run_verification
        records={};calls=[]
        def runtime(args,current,url,evidence):
            variant=next(name for name in docker_variant_verify.PLANS if pathlib.Path(evidence).parent.name.startswith(name+'-'))
            if variant.startswith('reference-'):return {'status':'PASS','mode':'TEST_CONTROL_ONLY'}
            if variant not in ('wrong-ready','wrong-seed-reset'):
                case,detail=('runtime_image_contents',{'marker':'C11_IMAGE_CONTENT_CHECK=1'}) if variant=='wrong-secret-copy' else ('sigterm_forced_kill',{'exit_code':137})
                pathlib.Path(evidence).mkdir()
                (pathlib.Path(evidence)/'docker-report.json').write_text(json.dumps({'status':'FAIL','mode':'TEST_CONTROL_ONLY'}))
                (pathlib.Path(evidence)/'docker-commands.json').write_text('[]')
                raise ContractViolation(case,detail)
            state={'seed_count':0,'stock':-1,'observed_target':False}
            def request(base,path,method='GET',**kw):
                label='other'
                if path=='/live':answer=(200,{'status':'UP'})
                elif path=='/downstream-check':
                    label='dependency_after' if state['observed_target'] else 'dependency_before'
                    answer=(200,{'status':'PONG','layer':'APPLICATION'})
                elif path=='/stock':
                    label='stock_after' if state['observed_target'] else 'stock_before'
                    answer=(503 if state['stock']==-1 else 200,{'stock':state['stock']})
                elif path=='/ready':
                    if state['seed_count']==0:
                        answer=(200,{'status':'READY','seeded':False}) if variant=='wrong-ready' else (503,{'status':'NOT_READY','seeded':False})
                        if variant=='wrong-ready':label='target';state['observed_target']=True
                    else:answer=(200,{'status':'READY','seeded':True})
                elif path.startswith('/orders?'):answer=(503,{'error':'NOT_SEEDED'})
                elif path=='/seed':
                    state['seed_count']+=1;state['stock']=10;answer=(200,{'created':True,'stock':10})
                    if state['seed_count']==2:label='target';state['observed_target']=True
                else:raise AssertionError('Unexpected HTTP call '+path)
                calls.append((variant,label,path,method))
                if variant==target and label==event and response is not None:
                    if isinstance(response,Exception):raise response
                    answer=copy.deepcopy(response)
                    if path=='/seed' and answer[0]==200 and isinstance(answer[1],dict) and type(answer[1].get('stock')) is int:state['stock']=answer[1]['stock']
                return answer
            def command(args,**kw):return subprocess.CompletedProcess(args,0,'28.0.0' if 'info' in args else '','')
            def urlopen(req,timeout):
                parsed=urllib.parse.urlsplit(req.full_url)
                path=parsed.path+('?' + parsed.query if parsed.query else '')
                code,body=request(url,path,req.get_method(),timeout=timeout)
                stream=io.BytesIO(json.dumps(body).encode())
                if code>=400:raise urllib.error.HTTPError(req.full_url,code,'mock HTTP response',None,stream)
                stream.status=code
                return stream
            try:
                with patch.object(contract.urllib.request,'urlopen',side_effect=urlopen),patch.object(docker_verify,'wait_status'),patch.object(docker_verify.subprocess,'run',side_effect=command):
                    return original(args,current,url,evidence)
            finally:
                records[variant]=json.loads((pathlib.Path(evidence)/'docker-report.json').read_text())
        with tempfile.TemporaryDirectory() as directory,patch.object(docker_variant_verify,'run_verification',side_effect=runtime):
            error=None
            try:docker_variant_verify.run_matrix(argv,env,'http://127.0.0.1:18085',directory)
            except Exception as caught:error=caught
            matrix=json.loads((pathlib.Path(directory)/'docker-variants.json').read_text())
        return error,matrix,records,calls

    def assert_rejected(self,target,event,response,infra=True):
        error,matrix,reports,calls=self.exercise(target,event,response)
        self.assertIsNotNone(error)
        self.assertEqual(matrix['status'],'FAIL')
        self.assertNotIn(target,[v['variant'] for v in matrix['variants']])
        report=reports[target]
        self.assertEqual(report['status'],'FAIL')
        self.assertTrue(any(v==target and e==event for v,e,_,_ in calls))
        if infra:
            self.assertIsInstance(error,VerificationInfrastructureError)
            self.assertEqual(report['failure']['classification'],'INFRASTRUCTURE')
        return error,report

    def test_both_precise_business_witnesses_are_accepted_through_full_path(self):
        error,matrix,reports,calls=self.exercise()
        self.assertIsNone(error);self.assertEqual(matrix['status'],'PASS')
        for variant in ('wrong-ready','wrong-seed-reset'):
            accepted=next(item for item in matrix['variants'] if item['variant']==variant)
            self.assertEqual(accepted['status'],'EXPECTED_SEMANTIC_FAILURE')
            self.assertEqual(accepted['observed_failure']['status'],200)
            self.assertEqual(reports[variant]['failure']['classification'],'CONTRACT_VIOLATION')
            self.assertTrue(any(item['classification']=='PASS' for item in reports[variant]['http_observations']))

    def test_second_seed_actual_stock_change_is_accepted(self):
        error,matrix,reports,_=self.exercise('wrong-seed-reset','target',(200,{'created':False,'stock':9}))
        self.assertIsNone(error);self.assertEqual(matrix['status'],'PASS')
        self.assertTrue(any(item['case_id']=='stock_after_second_seed' and item['body']=={'stock':9} for item in reports['wrong-seed-reset']['http_observations']))

    def test_ready_dependency_503_timeout_is_infrastructure(self):
        error,report=self.assert_rejected('wrong-ready','target',(503,{'error':'DEPENDENCY_UNAVAILABLE','layer':'TIMEOUT'}))
        self.assertEqual(error.detail['status'],503);self.assertEqual(error.detail['body']['layer'],'TIMEOUT')

    def test_second_seed_dependency_503_connect_is_infrastructure(self):
        self.assert_rejected('wrong-seed-reset','target',(503,{'error':'DEPENDENCY_UNAVAILABLE','layer':'CONNECT'}))

    def test_both_targets_reject_all_dependency_layers_and_unexpected_5xx(self):
        for variant in ('wrong-ready','wrong-seed-reset'):
            for layer in ('DNS','CONNECT','TIMEOUT','AUTH','PROTOCOL'):
                with self.subTest(variant=variant,layer=layer):
                    self.assert_rejected(variant,'target',(503,{'error':'DEPENDENCY_UNAVAILABLE','layer':layer}))
            for code in (500,502,503,504):
                with self.subTest(variant=variant,code=code):self.assert_rejected(variant,'target',(code,{'error':'UNAVAILABLE'}))

    def test_both_targets_reject_transport_timeout_connection_and_invalid_json(self):
        for variant in ('wrong-ready','wrong-seed-reset'):
            for error in (TimeoutError('mock timeout'),ConnectionResetError('mock reset'),urllib.error.URLError('mock DNS'),ValueError('mock JSON'),http.client.IncompleteRead(b'partial')):
                with self.subTest(variant=variant,error=type(error).__name__):self.assert_rejected(variant,'target',error)

    def test_ready_unrelated_fields_and_status_do_not_kill_target(self):
        for response in ((200,{'status':'READY','seeded':True}),(200,{'status':'UP','seeded':False}),(200,{'status':'READY'}),(200,{'status':'READY','seeded':0}),(201,{'status':'READY','seeded':False}),(404,{'error':'NOT_FOUND'})):
            with self.subTest(response=response):self.assert_rejected('wrong-ready','target',response,infra=False)

    def test_seed_missing_fields_wrong_types_and_non_success_do_not_kill_target(self):
        for response in ((200,{'created':True}),(200,{'created':1,'stock':10}),(200,{'created':False,'stock':'9'}),(201,{'created':True,'stock':10}),(400,{'error':'INVALID_REQUEST'})):
            with self.subTest(response=response):self.assert_rejected('wrong-seed-reset','target',response,infra=False)

    def test_healthy_target_with_dependency_precondition_failure_is_rejected(self):
        for variant in ('wrong-ready','wrong-seed-reset'):
            with self.subTest(variant=variant):self.assert_rejected(variant,'dependency_before',(503,{'error':'DEPENDENCY_UNAVAILABLE','layer':'CONNECT'}))

    def test_precise_target_with_failed_postcondition_is_rejected(self):
        for variant in ('wrong-ready','wrong-seed-reset'):
            with self.subTest(variant=variant):self.assert_rejected(variant,'dependency_after',TimeoutError('mock dependency after target'))

    def test_precise_target_with_inconsistent_stock_is_rejected(self):
        for variant in ('wrong-ready','wrong-seed-reset'):
            with self.subTest(variant=variant):self.assert_rejected(variant,'stock_after',(200,{'stock':999}),infra=False)

    def test_target_without_corresponding_report_witness_is_rejected(self):
        _,_,reports,_=self.exercise()
        for variant in ('wrong-ready','wrong-seed-reset'):
            original=reports[variant];failure=original['failure'];error=ContractViolation(failure['case_id'],failure['detail'])
            for field in ('http_observations','failure'):
                report=copy.deepcopy(original);report.pop(field)
                with self.subTest(variant=variant,field=field):self.assertFalse(docker_variant_verify.expected_semantic_failure(variant,error,report,[]))

    def test_exhausted_health_wait_is_infrastructure(self):
        with self.assertRaises(VerificationInfrastructureError) as caught:contract.wait_status('http://unused.invalid','/downstream-check',seconds=0)
        self.assertEqual(caught.exception.case_id,'wait_status')

if __name__=='__main__':unittest.main(verbosity=2)
