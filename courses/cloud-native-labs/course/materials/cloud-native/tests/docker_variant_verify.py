#!/usr/bin/env python3
"""作者用真实Docker正负例矩阵，由统一driver调用，不是另一个环境入口。

每个变体复制白名单材料到独立context、分配独立project/namespace；不改学习者源码。
没有Docker时整体NOT_RUN。只接受对应业务/镜像/信号断言失败，构建失败不算杀死错误解。
"""
import json,pathlib,re,shutil,uuid
from docker_verify import run_verification,validate_context
from verification_guard import ContractViolation,VerificationSetupError,claim_evidence,require_selection
ROOT=pathlib.Path(__file__).resolve().parents[1]
PLANS=['reference-exec','reference-exec-script','wrong-ready','wrong-seed-reset','wrong-secret-copy','wrong-shell-term']

def make_context(destination,variant):
    destination=pathlib.Path(destination);destination.mkdir(parents=True,exist_ok=False)
    for folder in ['src','web','container']:shutil.copytree(ROOT/folder,destination/folder)
    shutil.copy2(ROOT/'.dockerignore',destination/'.dockerignore')
    # 明确合成值，只存在于本验证上下文，正确白名单不应把它打包。
    (destination/'.env').write_text('COURSE_FAKE_TOKEN=NOT_A_REAL_CREDENTIAL\n')
    dockerfile=destination/'container/Dockerfile'
    if variant=='reference-exec-script':shutil.copy2(ROOT/'answers/Dockerfile.exec-script',dockerfile)
    elif variant=='wrong-ready':shutil.copy2(ROOT/'wrong/CloudPolicy-always-ready.java.txt',destination/'src/labs/CloudPolicy.java')
    elif variant=='wrong-seed-reset':
        path=destination/'src/labs/Inventory.java';source=path.read_text()
        anchor="        if redis.call('EXISTS', KEYS[1]) == 1 then return 0 end\n"
        assert source.count(anchor)==1,'Mutation anchor drift; do not run unmodified wrong solution'
        path.write_text(source.replace(anchor,''))
    elif variant=='wrong-secret-copy':
        source=dockerfile.read_text();anchor='USER 10001:10001'
        assert source.count(anchor)==1
        dockerfile.write_text(source.replace(anchor,'COPY . /opt/app/leak\n'+anchor))
        with (destination/'.dockerignore').open('a') as stream:stream.write('!.env\n')
    elif variant=='wrong-shell-term':
        source=dockerfile.read_text();anchor='ENTRYPOINT ["java", "-XX:MaxRAMPercentage=65.0", "-cp", "/opt/app/classes", "labs.CloudNativeApp"]'
        assert source.count(anchor)==1
        dockerfile.write_text(source.replace(anchor,'ENTRYPOINT ["sh", "-c", "trap \'\' TERM; java -cp /opt/app/classes labs.CloudNativeApp & wait"]'))
    elif variant!='reference-exec':raise ValueError('Unknown bounded variant')
    return destination

def expected_semantic_failure(variant,error,report,commands):
    expected={'wrong-ready':'ready_rejects_unseeded','wrong-seed-reset':'seed_is_idempotent',
              'wrong-secret-copy':'runtime_image_contents','wrong-shell-term':'sigterm_forced_kill'}
    if not isinstance(error,ContractViolation) or error.case_id!=expected.get(variant):return False
    if variant not in ('wrong-ready','wrong-seed-reset'):return True
    # case_id只定位断言，不证明为何失败。必须核对本次报告中的实际HTTP状态、字段及健康前后置观测。
    evidence=error.detail
    if not isinstance(evidence,dict) or report.get('status')!='FAIL' or report.get('cleanup_status'):return False
    if report.get('failure')!={'classification':'CONTRACT_VIOLATION','case_id':error.case_id,'detail':evidence}:return False
    observations=report.get('http_observations',[])
    if evidence not in observations or evidence.get('classification')!='CONTRACT_VIOLATION':return False
    if any(item.get('classification')=='INFRASTRUCTURE' for item in observations):return False
    position=observations.index(evidence)
    def witnessed(name,status,fields,after=False):
        selected=observations[position+1:] if after else observations[:position]
        return any(item.get('case_id')==name and item.get('classification')=='PASS' and item.get('status')==status and
                   isinstance(item.get('body'),dict) and
                   all(type(item['body'].get(k)) is type(v) and item['body'].get(k)==v for k,v in fields.items()) for item in selected)
    common=witnessed('live_before_seed',200,{'status':'UP'}) and witnessed('dependency_before_inventory',200,{'status':'PONG','layer':'APPLICATION'}) and witnessed('stock_before_seed',503,{'stock':-1})
    if not common or evidence.get('status')!=200:return False
    body=evidence.get('body')
    if not isinstance(body,dict) or 'error' in body or 'layer' in body:return False
    if variant=='wrong-ready':
        return (evidence.get('path')=='/ready' and evidence.get('method')=='GET' and
                body.get('status')=='READY' and body.get('seeded') is False and
                witnessed('dependency_after_ready_observation',200,{'status':'PONG','layer':'APPLICATION'},after=True) and
                witnessed('stock_after_ready_observation',503,{'stock':-1},after=True))
    return (evidence.get('path')=='/seed' and evidence.get('method')=='POST' and
            type(body.get('created')) is bool and type(body.get('stock')) is int and
            (body['created'] is True or body['stock']!=10) and
            witnessed('ready_rejects_unseeded',503,{'status':'NOT_READY','seeded':False}) and
            witnessed('orders_reject_unseeded',503,{'error':'NOT_SEEDED'}) and
            witnessed('seed_initializes_ten',200,{'created':True,'stock':10}) and
            witnessed('ready_after_seed',200,{'status':'READY','seeded':True}) and
            witnessed('dependency_before_second_seed',200,{'status':'PONG','layer':'APPLICATION'}) and
            witnessed('stock_before_second_seed',200,{'stock':10}) and
            witnessed('dependency_after_second_seed',200,{'status':'PONG','layer':'APPLICATION'},after=True) and
            witnessed('ready_after_second_seed',200,{'status':'READY','seeded':True},after=True) and
            witnessed('stock_after_second_seed',200,{'stock':body['stock']},after=True))

def run_matrix(compose_argv,env,base_url,evidence_dir):
    selected=require_selection(PLANS,['reference-exec','reference-exec-script','wrong-ready','wrong-seed-reset','wrong-secret-copy','wrong-shell-term'],'Docker variant matrix')
    if len(selected)!=6:raise VerificationSetupError('Full Docker matrix requires both references and all four negative variants')
    base_project=validate_context(compose_argv,env,base_url)
    evidence_dir=pathlib.Path(evidence_dir);context=claim_evidence(evidence_dir)
    results=[];matrix={'run_id':context['run_id'],'status':'FAIL','mode':'REAL_DOCKER_REFERENCE_AND_NEGATIVE_MATRIX','selected':selected,'variants':results}
    try:
        for variant in selected:
            token=uuid.uuid4().hex[:8];project=base_project.rsplit('-verify-',1)[0]+'-verify-'+token
            variant_dir=evidence_dir/(variant+'-'+token);variant_dir.mkdir()
            context=make_context(variant_dir/'context',variant)
            override=variant_dir/'compose.override.json'
            override.write_text(json.dumps({'services':{'cloudnative-api':{'build':{'context':str(context),'dockerfile':'container/Dockerfile'}}}},indent=2)+'\n')
            argv=compose_argv.copy();argv[argv.index('--project-name')+1]=project;argv.extend(['-f',str(override)])
            current=dict(env,LAB_PROJECT_NAME=project,CLOUDNATIVE_NAMESPACE='c11-verify-'+uuid.uuid4().hex[:16])
            try:
                report=run_verification(argv,current,base_url,variant_dir/'run')
                if report['status']=='NOT_RUN':
                    matrix['status']='NOT_RUN';matrix['reason']=report.get('reason');return matrix
                assert variant.startswith('reference-'),'Wrong solution unexpectedly passed all Docker assertions'
                assert report['status']=='PASS','Reference variant failed or cleanup failed'
                results.append({'variant':variant,'status':'PASS','evidence':variant_dir.name})
            except ContractViolation as error:
                report=json.loads((variant_dir/'run/docker-report.json').read_text())
                commands=json.loads((variant_dir/'run/docker-commands.json').read_text())
                if variant.startswith('reference-') or not expected_semantic_failure(variant,error,report,commands):raise
                if report.get('cleanup_status'):raise AssertionError('Cleanup failed; cannot accept negative variant') from error
                results.append({'variant':variant,'status':'EXPECTED_SEMANTIC_FAILURE','evidence':variant_dir.name,
                                'case_id':error.case_id,'observed_failure':error.detail})
        if len(results)!=len(selected):raise VerificationSetupError('Incomplete Docker matrix')
        matrix['status']='PASS';return matrix
    finally:(evidence_dir/'docker-variants.json').write_text(json.dumps(matrix,ensure_ascii=False,indent=2)+'\n')
