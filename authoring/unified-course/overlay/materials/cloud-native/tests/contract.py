"""业务调用方兼可复用断言；HTTP失败必须读回JSON，不能只断言容器running。"""
import http.client,json,time,urllib.request,urllib.error,concurrent.futures
from verification_guard import require_contract,VerificationInfrastructureError,ContractViolation
if not __debug__:raise RuntimeError("Grading requires Python assertions; do not use python -O")

def request(base,path,method='GET',timeout=3):
    req=urllib.request.Request(base+path,method=method)
    try:
        with urllib.request.urlopen(req,timeout=timeout) as response:
            return response.status,json.loads(response.read())
    except urllib.error.HTTPError as response:
        return response.code,json.loads(response.read())

def wait_status(base,path,want=200,seconds=12):
    deadline=time.monotonic()+seconds
    last='not attempted'
    while time.monotonic()<deadline:
        try:
            last=request(base,path)
            if last[0]==want:return last
        except (OSError,ValueError,http.client.HTTPException) as error:last=type(error).__name__
        time.sleep(.1)
    raise VerificationInfrastructureError('wait_status',{'path':path,'expected_status':want,'last':last})

def fresh_inventory_contract(base,prefix='contract',observations=None,passed_cases=None):
    """仅在验证器新分配的namespace上执行。绝不清空旧用户库存。"""
    results=passed_cases if passed_cases is not None else []
    observations=observations if observations is not None else []
    def check(name,path,status,fields,method='GET',postcheck=None):
        evidence={'case_id':name,'path':path,'method':method,'expected_status':status,
                  'expected_fields':fields,'previous_cases':list(results)}
        observations.append(evidence)
        try:
            code,body=request(base,path,method)
        except (OSError,ValueError,http.client.HTTPException) as error:
            evidence.update(classification='INFRASTRUCTURE',transport_error=type(error).__name__)
            raise VerificationInfrastructureError(name,evidence) from error
        evidence.update(status=code,body=body)
        # 仅显式的未就绪/未初始化业务响应允许HTTP503。依赖、传输及其他5xx单独分类。
        allowed_503=(code==503 and isinstance(body,dict) and (
            (path=='/ready' and body.get('status')=='NOT_READY' and type(body.get('seeded')) is bool) or
            (path.startswith('/orders?') and body=={'error':'NOT_SEEDED'}) or
            (path=='/stock' and body=={'stock':-1})))
        dependency_error=isinstance(body,dict) and (body.get('error') in ('DEPENDENCY_UNAVAILABLE','DRAINING','INTERRUPTED') or
            body.get('layer') in ('DNS','CONNECT','TIMEOUT','AUTH','PROTOCOL'))
        if type(code) is not int or not isinstance(body,dict) or dependency_error or (code>=500 and not allowed_503):
            evidence['classification']='INFRASTRUCTURE'
            raise VerificationInfrastructureError(name,evidence)
        matched=code==status and all(type(body.get(k)) is type(v) and body.get(k)==v for k,v in fields.items())
        evidence['classification']='PASS' if matched else 'CONTRACT_VIOLATION'
        if not matched:
            # 目标错误前后的依赖与库存观测必须健康。后置观测失败优先作为本次失败返回。
            if postcheck is not None:postcheck(body)
            raise ContractViolation(name,evidence)
        results.append(name)
        return body
    check('live_before_seed','/live',200,{'status':'UP'})
    check('dependency_before_inventory','/downstream-check',200,{'status':'PONG','layer':'APPLICATION'})
    check('stock_before_seed','/stock',503,{'stock':-1})
    def ready_postcheck(body):
        check('dependency_after_ready_observation','/downstream-check',200,{'status':'PONG','layer':'APPLICATION'})
        check('stock_after_ready_observation','/stock',503,{'stock':-1})
    check('ready_rejects_unseeded','/ready',503,{'status':'NOT_READY','seeded':False},postcheck=ready_postcheck)
    check('orders_reject_unseeded',f'/orders?request_id={prefix}-1&quantity=2',503,{'error':'NOT_SEEDED'},'POST')
    check('seed_initializes_ten','/seed',200,{'created':True,'stock':10},'POST')
    check('ready_after_seed','/ready',200,{'status':'READY','seeded':True})
    check('dependency_before_second_seed','/downstream-check',200,{'status':'PONG','layer':'APPLICATION'})
    check('stock_before_second_seed','/stock',200,{'stock':10})
    def seed_postcheck(body):
        check('dependency_after_second_seed','/downstream-check',200,{'status':'PONG','layer':'APPLICATION'})
        check('ready_after_second_seed','/ready',200,{'status':'READY','seeded':True})
        if type(body.get('stock')) is int:
            check('stock_after_second_seed','/stock',200,{'stock':body['stock']})
    check('seed_is_idempotent','/seed',200,{'created':False,'stock':10},'POST',postcheck=seed_postcheck)
    check('reserve_decrements_once',f'/orders?request_id={prefix}-1&quantity=2',201,{'status':'CREATED','remaining':8},'POST')
    check('replay_does_not_double_charge',f'/orders?request_id={prefix}-1&quantity=2',200,{'status':'REPLAY','remaining':8},'POST')
    check('changed_payload_conflicts',f'/orders?request_id={prefix}-1&quantity=3',409,{'error':'CONFLICT'},'POST')
    check('seed_does_not_refill','/seed',200,{'created':False,'stock':8},'POST')
    for qty in ['0','-1','11','not-number']:
        check('invalid_quantity_'+qty,f'/orders?request_id={prefix}-bad&quantity={qty}',400,{'error':'INVALID_REQUEST'},'POST')
    check('duplicate_query_rejected',f'/orders?request_id={prefix}-bad&quantity=1&quantity=2',400,{'error':'INVALID_REQUEST'},'POST')
    check('sold_out_does_not_mutate',f'/orders?request_id={prefix}-large&quantity=9',409,{'error':'SOLD_OUT'},'POST')
    check('stock_remains_eight','/stock',200,{'stock':8})
    # 并发的8份库存只允许8个请求成功，其余必须明确SOLD_OUT。
    with concurrent.futures.ThreadPoolExecutor(max_workers=12) as pool:
        responses=list(pool.map(lambda i:request(base,f'/orders?request_id={prefix}-parallel-{i}&quantity=1','POST'),range(12)))
    assert sum(code==201 for code,_ in responses)==8,responses
    assert sum(code==409 and body.get('error')=='SOLD_OUT' for code,body in responses)==4,responses
    check('no_oversell','/stock',200,{'stock':0})
    results.append('concurrent_no_oversell')
    return results
