#!/usr/bin/env python3
"""公开YAML合同，不把静态字段检查冒充Kubernetes行为验证。"""
import argparse,json,pathlib,sys
try:import yaml
except ImportError:print('{"status":"INVALID_ENV","reason":"PYYAML_REQUIRED"}');sys.exit(2)

def errors(task,directory):
    d=pathlib.Path(directory);result=[]
    def check(ok,name):
        if not ok:result.append(name)
    def read(name):return yaml.safe_load((d/name).read_text())
    if task in ('C11-04','C11-06'):
        x=read('deployment.yaml');s=x['spec'];c=s['template']['spec']['containers'][0]
        check(s['selector']['matchLabels'].items()<=s['template']['metadata']['labels'].items(),'SELECTOR_MATCHES_POD_LABELS')
        for probe,path in [('startupProbe','/startup'),('readinessProbe','/ready'),('livenessProbe','/live')]:
            check(c.get(probe,{}).get('httpGet',{}).get('path')==path,probe.upper()+'_ENDPOINT')
        startup=c.get('startupProbe',{});check(startup.get('failureThreshold',0)*startup.get('periodSeconds',0)>8,'STARTUP_BUDGET_GT_INITIALIZATION')
        check(s['template']['spec'].get('terminationGracePeriodSeconds',0)>=6,'TERM_BUDGET')
        if task=='C11-06':
            check(s['replicas']==2,'TWO_REPLICAS')
            strategy=s.get('strategy',{});rolling=strategy.get('rollingUpdate',{})
            check(strategy.get('type')=='RollingUpdate' and rolling.get('maxUnavailable')==0 and rolling.get('maxSurge')==1,'BOUNDED_ROLLOUT_STRATEGY')
            check(2<=s.get('revisionHistoryLimit',0)<=5,'ROLLBACK_HISTORY')
            check(30<=s.get('progressDeadlineSeconds',0)<=120,'BOUNDED_PROGRESS_DEADLINE')
            r=c.get('resources',{});check(r.get('requests')=={'cpu':'100m','memory':'128Mi'},'REQUEST_BUDGET');check(r.get('limits')=={'cpu':'500m','memory':'256Mi'},'LIMIT_BUDGET')
    elif task=='C11-05':
        service=read('service.yaml')['spec'];check(service.get('selector')=={'app':'orders'},'SERVICE_SELECTOR');check(service.get('type')=='ClusterIP','CLUSTERIP_ONLY');check(service.get('ports')==[{'name':'http','port':8080,'targetPort':'http'}],'SERVICE_PORT_CHAIN')
        config=read('config.yaml')['data'];check(config.get('redis-host')=='redis','REDIS_SERVICE_DNS');check(not any('password' in k.lower() or 'secret' in k.lower() for k in config),'NO_SECRET_IN_CONFIGMAP')
        resources=read('rbac.yaml')['items'];role=next(x for x in resources if x['kind']=='Role');rules=role['rules']
        check(all(set(r['verbs'])<={'get','list'} and '*' not in r['resources'] and 'secrets' not in r['resources'] for r in rules),'RBAC_LEAST_PRIVILEGE')
        check(all(x.get('automountServiceAccountToken') is False for x in resources if x['kind']=='ServiceAccount'),'TOKEN_AUTOMOUNT_OFF')
    else:raise ValueError('unknown task')
    return result

def main():
    p=argparse.ArgumentParser();p.add_argument('--task',required=True,choices=['C11-04','C11-05','C11-06']);p.add_argument('--task-dir',type=pathlib.Path,required=True);a=p.parse_args()
    try:found=errors(a.task,a.task_dir)
    except (OSError,KeyError,TypeError,ValueError,yaml.YAMLError):print('{"status":"FAIL","reason":"TASK_YAML_PARSE_OR_SHAPE"}');return 1
    print(json.dumps({'status':'FAIL' if found else 'YAML_CONTRACT_PASS','failures':found,'java_semantics':'NOT_CHECKED_HERE','kind_e2e':'NOT_CHECKED_HERE'}));return 1 if found else 0
if __name__=='__main__':sys.exit(main())
