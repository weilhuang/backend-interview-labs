"""真实Kind观测。单元测试可mock调用顺序，但只有这些实际运行才是E2E。"""
import copy,json,time
from lab import LabError,require,LABEL

def check(ok,reason):require(ok,reason,'FAIL')
def restart_count(p):return sum(c.get('restartCount',0) for c in p.get('status',{}).get('containerStatuses',[]))
def ready(p):return bool(p.get('status',{}).get('containerStatuses')) and all(c.get('ready',False) for c in p['status']['containerStatuses'])
def patch(lab,kind,name,value):
    lab.own(kind,name)
    lab.kubectl('patch',kind,name,'--type=merge','-p',json.dumps(value))
def healthy(lab):
    r=lab.call('/info');check(r['status']==200,'BASELINE_HTTP_NOT_OK')
    check(len([p for p in lab.api_pods() if ready(p)])==2,'BASELINE_TWO_READY_REQUIRED')
    return r['body']
def ready_endpoint_uids(lab):
    # EndpointSlices由Service controller创建，不伪造课程标签。
    result=json.loads(lab.kubectl('get','endpointslices','-l','kubernetes.io/service-name=orders','-o','json').stdout)
    return {e.get('targetRef',{}).get('uid') for item in result['items'] for e in item.get('endpoints',[]) if e.get('conditions',{}).get('ready') is True}
def baseline(lab):
    healthy(lab);request='baseline-'+lab.state['run']
    a=lab.call('/orders?request_id='+request+'&quantity=2','POST')
    stock_before_replay=lab.call('/stock');check(stock_before_replay['status']==200,'STOCK_WITNESS_MISSING')
    b=lab.call('/orders?request_id='+request+'&quantity=2','POST')
    stock_after_replay=lab.call('/stock');check(stock_after_replay['status']==200,'STOCK_WITNESS_MISSING')
    check(stock_before_replay['body']['stock']==stock_after_replay['body']['stock'],'REPLAY_CHANGED_LIVE_STOCK')
    check(a['status'] in (200,201) and b['status']==200 and b['body']['status']=='REPLAY','IDEMPOTENCY_FAILED')
    check(a['body']['remaining']==b['body']['remaining'],'REPLAY_CHANGED_STOCK')
    # 幂等响应保留原订单当时的remaining；其他合法订单可令当前库存更低。
    c=lab.call('/seed','POST');check(c['status']==200 and c['body']['created'] is False and c['body']['stock']==stock_after_replay['body']['stock'],'SEED_REFILLED_STOCK')
    return {'case':'baseline','status':'PASS','request_id':request,'remaining':b['body']['remaining']}
def probes(lab):
    healthy(lab);target=lab.api_pods()[0];name=target['metadata']['name'];uid=target['metadata']['uid'];before=restart_count(target)
    lab.exec_java(name,'FixtureCtl','not-ready','on')
    try:
        lab.eventually(lambda:uid not in ready_endpoint_uids(lab),reason='NOT_READY_STILL_ROUTED')
        check(lab.call('/ready',pod=name,host='127.0.0.1',allow_failure=True)['status']==503,'READINESS_NEGATIVE_WITNESS_MISSING')
        check(lab.call('/live',pod=name,host='127.0.0.1')['status']==200,'READINESS_DAMAGED_LIVENESS')
        time.sleep(8)
        check(restart_count(lab.get('pod',name))==before,'READINESS_RESTARTED_CONTAINER')
        check(lab.call('/info')['status']==200,'OTHER_REPLICA_NOT_SERVING')
    finally:lab.exec_java(name,'FixtureCtl','not-ready','off')
    lab.eventually(lambda:uid in ready_endpoint_uids(lab),reason='READINESS_NOT_RECOVERED')
    original=lab.own('service','redis')['spec']['selector']
    patch(lab,'service','redis',{'spec':{'selector':{**original,'app':'redis-missing'}}})
    counts={p['metadata']['name']:restart_count(p) for p in lab.api_pods()}
    try:
        lab.eventually(lambda:not ready_endpoint_uids(lab),reason='DEPENDENCY_OUTAGE_NOT_OBSERVED')
        for pname in counts:
            check(lab.call('/ready',pod=pname,host='127.0.0.1',allow_failure=True)['status']==503,'DEPENDENCY_READINESS_WITNESS_MISSING')
            check(lab.call('/live',pod=pname,host='127.0.0.1')['status']==200,'DEPENDENCY_KILLED_LIVENESS')
        time.sleep(8)
        for pname,count in counts.items():check(restart_count(lab.get('pod',pname))==count,'DEPENDENCY_RESTART_STORM')
    finally:patch(lab,'service','redis',{'spec':{'selector':original}})
    lab.rollout();healthy(lab)
    lab.exec_java(name,'FixtureCtl','not-live','on')
    lab.eventually(lambda:restart_count(lab.get('pod',name))>before,reason='LIVENESS_DID_NOT_RESTART')
    lab.eventually(lambda:ready(lab.get('pod',name)),reason='LIVENESS_NOT_RECOVERED')
    # 只有受控Pod名称/UID通过own后才能删除；观察新UID，不能只count=2。
    lab.own('pod',name);lab.kubectl('delete','pod',name,'--wait=false')
    lab.eventually(lambda:len(lab.api_pods())==2 and all(p['metadata']['uid']!=uid and ready(p) for p in lab.api_pods()),reason='DEPLOYMENT_DID_NOT_REPLACE_POD')
    healthy(lab)
    return {'case':'probes','status':'PASS','evidence':['503 ready / 200 live','EndpointSlice removed then restored','dependency outage without restart','local liveness restart','replacement Pod has new UID']}
def config(lab):
    initial=healthy(lab);ns=lab.state['namespace'];fqdn='orders.'+ns+'.svc.cluster.local'
    check(lab.call('/info',host=fqdn)['status']==200,'SERVICE_FQDN_FAILED')
    original=lab.own('service','orders')['spec']['selector']
    patch(lab,'service','orders',{'spec':{'selector':{**original,'app':'orders-missing'}}})
    try:
        lab.eventually(lambda:not ready_endpoint_uids(lab),reason='BAD_SELECTOR_DID_NOT_REMOVE_ENDPOINTS')
        check(len([p for p in lab.api_pods() if ready(p)])==2,'SELECTOR_CHANGED_POD_HEALTH')
    finally:patch(lab,'service','orders',{'spec':{'selector':original}})
    lab.eventually(lambda:len(ready_endpoint_uids(lab))==2,reason='SERVICE_NOT_RECOVERED')
    expected={p['metadata']['name']:p['metadata']['uid'] for p in lab.api_pods()}
    check(len(expected)==2,'CONFIG_EXPECTED_TWO_REPLICAS')
    cm=copy.deepcopy(lab.own('configmap','orders-config')['data'])
    patch(lab,'configmap','orders-config',{'data':{'greeting':'hello-v2','banner':'banner-v2'}})
    try:
        def all_original_replicas_reloaded():
            current={p['metadata']['name']:p['metadata']['uid'] for p in lab.api_pods()}
            check(current==expected,'CONFIG_REPLICAS_CHANGED_WITHOUT_REQUESTED_RESTART')
            converged=True
            for name in expected:
                response=lab.call('/info',pod=name,host='127.0.0.1')
                check(response['status']==200,'CONFIG_POD_HTTP_NOT_OK')
                value=response['body']
                check(value['greetingEnv']==initial['greetingEnv'],'ENV_CHANGED_WITHOUT_RESTART')
                converged=converged and value['bannerFile']=='banner-v2'
            return converged
        lab.eventually(all_original_replicas_reloaded,seconds=180,reason='PROJECTED_CONFIG_NOT_RELOADED_ON_ALL_REPLICAS')
        lab.own('deployment','orders');lab.kubectl('rollout','restart','deployment/orders');lab.rollout()
        replacement=lab.api_pods();check(len(replacement)==2 and all(ready(p) and p['metadata']['uid'] not in expected.values() for p in replacement),'CONFIG_RESTART_REPLACEMENT_NOT_PROVEN')
        for p in replacement:
            response=lab.call('/info',pod=p['metadata']['name'],host='127.0.0.1')
            check(response['status']==200 and response['body']['greetingEnv']=='hello-v2' and response['body']['bannerFile']=='banner-v2','CONFIG_NOT_UPDATED_ON_ALL_REPLACEMENTS')
        actor='system:serviceaccount:'+ns+':observer'
        for verb,resource,want,scope in [('get','pods',True,ns),('create','pods',False,ns),('get','secrets',False,ns),('get','pods',False,'default')]:
            # 仅鉴权模拟，不取得SA token，不创建新持久凭据。
            r=lab.kubectl('auth','can-i',verb,resource,'--as='+actor,'--namespace='+scope,allow_failure=True)
            answer=r.stdout.strip();require(answer in ('yes','no'),'RBAC_CHECK_NO_WITNESS')
            check((answer=='yes')==want,'RBAC_SCOPE_VIOLATION')
        # 从内存读合成Secret后扫描应用日志，只产布尔结果；不写原文、hash或base64。
        import base64
        synthetic=base64.b64decode(lab.get('secret','redis-auth')['data']['password']).decode()
        for p in lab.api_pods():
            log=lab.kubectl('logs',p['metadata']['name'],'--tail=200').stdout
            check(synthetic not in log and base64.b64encode(synthetic.encode()).decode() not in log,'SECRET_LEAKED_IN_APP_LOG')
        synthetic=None
    finally:
        patch(lab,'configmap','orders-config',{'data':cm});lab.own('deployment','orders');lab.kubectl('rollout','restart','deployment/orders');lab.rollout()
    healthy(lab)
    return {'case':'config','status':'PASS','evidence':['Service short/FQDN DNS','bad selector no ready endpoints','file eventually updated / env snapshot unchanged','restart loads env','RBAC allow+deny','no synthetic secret in app logs']}
def rollout(lab):
    healthy(lab);dep=lab.own('deployment','orders');previous=dep['spec']['template']['spec']['containers'][0]['image']
    target=lab.state['images']['v2'];samples=[];reset_to_v1=False
    def update(image):lab.own('deployment','orders');lab.kubectl('set','image','deployment/orders','api='+image)
    # 重跑仍必须观察真实模板变化，不能把v2→v2的空操作当滚动发布。
    if previous==target:
        update(lab.state['images']['v1']);lab.rollout();healthy(lab)
        check(all(p['spec']['containers'][0]['image']==lab.state['images']['v1'] for p in lab.api_pods()),'V1_BASELINE_NOT_CONVERGED')
        check(lab.call('/info')['body'].get('release')=='v1','V1_BASELINE_HTTP_NOT_PROVEN')
        previous=lab.state['images']['v1'];reset_to_v1=True
    check(previous==lab.state['images']['v1'] and previous!=target,'ROLLOUT_REQUIRES_DISTINCT_V1_BASELINE')
    update(target)
    deadline=time.monotonic()+120
    while time.monotonic()<deadline:
        d=lab.own('deployment','orders');r=lab.call('/info');samples.append({'status':r['status'],'release':r['body'].get('release'),'available':d.get('status',{}).get('availableReplicas',0)})
        check(r['status']==200 and samples[-1]['available']>=2,'ROLLING_AVAILABILITY_GAP')
        if d.get('status',{}).get('updatedReplicas')==2 and d.get('status',{}).get('replicas')==2 and r['body'].get('release')=='v2' and len(samples)>=10:break
        time.sleep(1)
    else:raise LabError('FAIL','V2_ROLLOUT_TIMEOUT')
    lab.rollout();v2revision=lab.own('deployment','orders')['metadata']['annotations']['deployment.kubernetes.io/revision']
    update(lab.state['images']['broken'])
    def stalled():
        d=lab.own('deployment','orders')
        return any(c.get('type')=='Progressing' and c.get('status')=='False' and c.get('reason')=='ProgressDeadlineExceeded' for c in d.get('status',{}).get('conditions',[]))
    try:
        lab.eventually(stalled,seconds=150,reason='BROKEN_ROLLOUT_WAS_NOT_BLOCKED')
        broken=[p for p in lab.api_pods() if p['spec']['containers'][0]['image']==lab.state['images']['broken']]
        check(bool(broken),'BROKEN_POD_MISSING')
        bp=broken[0]['metadata']['name']
        check(lab.call('/ready',pod=bp,host='127.0.0.1',allow_failure=True)['status']==503,'BROKEN_READY_WITNESS_MISSING')
        check(lab.call('/live',pod=bp,host='127.0.0.1')['status']==200,'BROKEN_FIXTURE_NOT_LIVE')
        check(lab.call('/info')['body']['release']=='v2','BROKEN_VERSION_RECEIVED_SERVICE_TRAFFIC')
    finally:
        lab.own('deployment','orders');lab.kubectl('rollout','undo','deployment/orders','--to-revision='+v2revision);lab.rollout()
    check(lab.call('/info')['body']['release']=='v2','ROLLBACK_DID_NOT_RECOVER_V2')
    return {'case':'rollout','status':'PASS','from_image':previous,'reset_to_v1':reset_to_v1,'samples':samples,'rollback_revision':v2revision,'evidence':['v2 serves business traffic','ProgressDeadlineExceeded','broken /ready=503 and /live=200','explicit revision rollback restores v2']}
def resources(lab):
    healthy(lab);dep=lab.own('deployment','orders');original=copy.deepcopy(dep['spec']['template']['spec']['containers'][0]['resources'])
    # 单节点总allocatable先证明低于故障request，保证该Pod只Pending不会实际申请巨量内存。
    node=lab.get('node',lab.state['name']+'-control-plane');cpu=node['status']['allocatable']['cpu'];millicores=int(cpu[:-1]) if cpu.endswith('m') else int(cpu)*1000
    require(millicores<1000000,'FAULT_REQUEST_NOT_GUARANTEED_UNSCHEDULABLE')
    def set_resources(value):
        d=lab.own('deployment','orders');containers=d['spec']['template']['spec']['containers'];containers[0]['resources']=value
        patch(lab,'deployment','orders',{'spec':{'template':{'spec':{'containers':containers}}}})
    try:
        bad=copy.deepcopy(original);bad['requests']['cpu']='1000000m';bad['limits']['cpu']='1000000m';set_resources(bad)
        def witness():
            return any(p.get('status',{}).get('phase')=='Pending' and any(c.get('type')=='PodScheduled' and c.get('status')=='False' and c.get('reason')=='Unschedulable' for c in p.get('status',{}).get('conditions',[])) for p in lab.api_pods())
        lab.eventually(witness,reason='UNSCHEDULABLE_WITNESS_MISSING')
        pending=next(p for p in lab.api_pods() if p.get('status',{}).get('phase')=='Pending')
        events=json.loads(lab.kubectl('get','events','--field-selector','involvedObject.uid='+pending['metadata']['uid'],'-o','json').stdout)['items']
        check(any(e.get('reason')=='FailedScheduling' and 'Insufficient cpu' in e.get('message','') for e in events),'INSUFFICIENT_CPU_EVENT_MISSING')
        check(lab.call('/info')['status']==200,'PENDING_ROLLOUT_DAMAGED_OLD_VERSION')
    finally:set_resources(original);lab.rollout()
    healthy(lab)
    return {'case':'resources','status':'PASS','evidence':['request exceeds observed node allocatable','Pending / Unschedulable / FailedScheduling Insufficient cpu','restore budget then ready'],'not_claimed':['OOMKilled real fixture','CPU throttling measurement','metrics-server','HPA capacity proof']}
def verify(lab,scenario):
    results=[baseline(lab)]
    if scenario=='all':results.append(lab.pod_demo())
    for name,fn in [('probes',probes),('config',config),('rollout',rollout),('resources',resources)]:
        if scenario in ('all',name):results.append(fn(lab))
    return {'status':'PASS','kind_e2e':True,'scenarios':results,'secret_or_kubeconfig_exported':False}
