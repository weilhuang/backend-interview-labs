#!/usr/bin/env python3
"""仅管理本程序创建的单节点kind实验。所有真实验证都fail-closed，绝不读取默认kubeconfig。"""
import argparse, base64, copy, hashlib, json, os, pathlib, re, secrets, shutil, stat, subprocess, sys, time
try:
    import yaml
except ImportError:
    print('{"status":"INVALID_ENV","reason":"PYYAML_REQUIRED"}');sys.exit(2)

ROOT=pathlib.Path(__file__).resolve().parents[1]
RUNTIME=ROOT/'.runtime'
LABEL='academy.openai.local/run'
TASKS={'C11-04':{'ProbePolicy.java':'src/labs/ProbePolicy.java','deployment.yaml':'manifests/deployment.yaml'},
       'C11-05':{'AppConfig.java':'src/labs/AppConfig.java','service.yaml':'manifests/service.yaml','config.yaml':'manifests/config.yaml','rbac.yaml':'manifests/rbac.yaml'},
       'C11-06':{'deployment.yaml':'manifests/deployment.yaml'}}

class LabError(Exception):
    def __init__(self,status,reason):super().__init__(reason);self.status=status;self.reason=reason
def require(ok,reason,status='INVALID_ENV'):
    if not ok:raise LabError(status,reason)
def execute(args,*,input=None,timeout=60,allow_failure=False,env=None):
    try:r=subprocess.run(args,input=input,text=True,capture_output=True,timeout=timeout,env=env)
    except (OSError,subprocess.TimeoutExpired):raise LabError('INVALID_ENV','COMMAND_UNAVAILABLE_OR_TIMEOUT')
    if r.returncode and not allow_failure:raise LabError('INVALID_ENV','COMMAND_FAILED')
    return r
def read_versions(path):
    values={}
    for line in pathlib.Path(path).read_text().splitlines():
        if not line.strip() or line.startswith('#'):continue
        require(re.fullmatch(r'[A-Z][A-Z0-9_]*=[A-Za-z0-9_./:@+\-]+',line) is not None,'INVALID_VERSION_LEDGER')
        k,v=line.split('=',1);require(k not in values,'DUPLICATE_VERSION_KEY');values[k]=v
    for k in ('JAVA_BUILD_IMAGE','JAVA_RUNTIME_IMAGE','REDIS_IMAGE','KIND_NODE_IMAGE','KIND_VERSION','KUBECTL_VERSION','KUBERNETES_VERSION'):
        require(k in values,'MISSING_VERSION_'+k)
    for k in ('JAVA_BUILD_IMAGE','JAVA_RUNTIME_IMAGE','KIND_NODE_IMAGE'):
        require(re.fullmatch(r'[^\s]+@sha256:[a-f0-9]{64}',values[k]) is not None,'UNPINNED_'+k)
    require(values['KUBECTL_VERSION']==values['KUBERNETES_VERSION'],'CLIENT_SERVER_PIN_MISMATCH')
    require(':latest' not in values['REDIS_IMAGE'] and ':' in values['REDIS_IMAGE'],'UNPINNED_REDIS')
    return values
def preflight(versions):
    require(yaml.__version__=='6.0.3','PYYAML_VERSION_MISMATCH')
    for name in ('docker','kind','kubectl'):require(shutil.which(name) is not None,'MISSING_'+name.upper())
    require(not os.environ.get('DOCKER_HOST') and not os.environ.get('DOCKER_CONTEXT'),'DOCKER_OVERRIDE_FORBIDDEN')
    endpoint=execute(['docker','context','inspect','--format','{{.Endpoints.docker.Host}}']).stdout.strip()
    require(endpoint.startswith('unix://'),'LOCAL_DOCKER_SOCKET_REQUIRED')
    info=json.loads(execute(['docker','info','--format','{{json .}}']).stdout)
    require(info.get('OSType')=='linux','LINUX_CONTAINERS_REQUIRED')
    require(info.get('NCPU',0)>=2 and info.get('MemTotal',0)>=3*1024**3,'NEED_2CPU_3G_DOCKER')
    require(info.get('CgroupVersion')=='2','CGROUP_V2_REQUIRED')
    require(versions['KIND_VERSION'] in execute(['kind','version']).stdout.split(),'KIND_VERSION_MISMATCH')
    client=json.loads(execute(['kubectl','version','--client','-o','json']).stdout)
    require(client.get('clientVersion',{}).get('gitVersion')==versions['KUBECTL_VERSION'],'KUBECTL_VERSION_MISMATCH')
def dump(path,value):
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n');path.chmod(0o600)
def image_tag(run,release):return f'c11-kind-api-{run}:{release}'
def safe_documents(documents,namespace,run,images):
    """练习YAML仍经过安全上限；不把声明式输入当任意集群管理权限。"""
    out=[]
    for obj in documents:
        if obj.get('kind')=='List':out.extend(safe_documents(obj['items'],namespace,run,images));continue
        kind=obj.get('kind');require(kind in {'Deployment','Service','ConfigMap','ServiceAccount','Role','RoleBinding','Pod'},'KIND_NOT_ALLOWED')
        meta=obj.setdefault('metadata',{});require(meta.get('name') in {'orders','redis','caller','solo-orders','orders-config','observer','course-observer'},'RESOURCE_NOT_ALLOWED')
        require(meta.get('namespace',namespace)==namespace,'NAMESPACE_OVERRIDE')
        meta['namespace']=namespace;meta.setdefault('labels',{})[LABEL]=run
        spec=obj.get('spec',{})
        if kind=='Service':require(spec.get('type','ClusterIP')=='ClusterIP' and not spec.get('externalIPs') and not spec.get('externalName'),'PUBLIC_SERVICE_FORBIDDEN')
        if kind=='Deployment':
            require(0<=spec.get('replicas',1)<=2,'REPLICA_BUDGET');spec['template']['metadata'].setdefault('labels',{})[LABEL]=run
            spec.setdefault('selector',{}).setdefault('matchLabels',{})[LABEL]=run
        if kind=='Service':spec.setdefault('selector',{})[LABEL]=run
        pod=spec.get('template',{}).get('spec') if kind=='Deployment' else spec if kind=='Pod' else None
        if pod is not None:
            require(not any(pod.get(k) for k in ('hostNetwork','hostPID','hostIPC','nodeName','initContainers','ephemeralContainers')),'HOST_ACCESS_FORBIDDEN')
            require(pod.get('automountServiceAccountToken') is False,'TOKEN_MOUNT_FORBIDDEN')
            sc=pod.get('securityContext',{});require(sc.get('runAsNonRoot') is True and sc.get('runAsUser')==10001,'NONROOT_REQUIRED')
            require(sc.get('seccompProfile',{}).get('type')=='RuntimeDefault','SECCOMP_REQUIRED')
            require(len(pod.get('containers',[]))==1,'SINGLE_CONTAINER_REQUIRED')
            for c in pod['containers']:
                require(c.get('image') in images and c.get('imagePullPolicy')=='Never','IMAGE_NOT_OWNED')
                cs=c.get('securityContext',{});require(cs.get('allowPrivilegeEscalation') is False and cs.get('readOnlyRootFilesystem') is True and cs.get('capabilities',{}).get('drop')==['ALL'] and not cs.get('privileged') and not cs.get('capabilities',{}).get('add'),'CONTAINER_SECURITY_REQUIRED')
                require(not any(p.get('hostPort') for p in c.get('ports',[])),'HOST_PORT_FORBIDDEN')
                r=c.get('resources',{});limits=r.get('limits',{})
                require(limits.get('cpu') in ('250m','500m') and limits.get('memory') in ('128Mi','256Mi'),'RESOURCE_LIMIT_OUTSIDE_COURSE_BUDGET')
            for v in pod.get('volumes',[]):
                require(set(v).issubset({'name','emptyDir','secret','configMap'}),'VOLUME_NOT_ALLOWED')
                if 'emptyDir' in v:require(v['emptyDir'].get('sizeLimit') in ('16Mi','32Mi','64Mi'),'VOLUME_BUDGET_REQUIRED')
        if kind=='Role':
            for rule in obj['rules']:
                require(set(rule['verbs'])<={'get','list'} and set(rule['resources'])<={'pods','services','events','deployments','replicasets','endpointslices'},'RBAC_EXPANSION_FORBIDDEN')
                require(not rule.get('nonResourceURLs'),'NONRESOURCE_RBAC_FORBIDDEN')
        if kind=='RoleBinding':
            require(obj['roleRef']=={'apiGroup':'rbac.authorization.k8s.io','kind':'Role','name':'course-observer'},'ROLE_BINDING_SCOPE')
            require(obj['subjects']==[{'kind':'ServiceAccount','name':'observer','namespace':namespace}],'RBAC_SUBJECT_SCOPE')
        out.append(obj)
    return out

class Lab:
    def __init__(self):
        self.statefile=RUNTIME/'state.json';self.state=None
    def load(self):
        require(self.statefile.is_file() and not self.statefile.is_symlink(),'NO_OWNED_STATE')
        require(stat.S_IMODE(self.statefile.stat().st_mode)==0o600,'STATE_PERMISSIONS')
        self.state=json.loads(self.statefile.read_text());s=self.state
        require(re.fullmatch('[a-f0-9]{12}',s.get('run','')) is not None,'BAD_RUN_ID')
        require(s.get('name')=='c11-kind-'+s['run'] and s.get('namespace')==s['name'],'BAD_OWNERSHIP')
        return s
    def save(self):dump(self.statefile,self.state)
    def kubectl(self,*args,input=None,timeout=60,allow_failure=False):
        s=self.state
        return execute(['kubectl','--kubeconfig',str(RUNTIME/'kubeconfig'),'--context','kind-'+s['name'],'--namespace',s['namespace'],'--request-timeout=15s',*args],input=input,timeout=timeout,allow_failure=allow_failure)
    def get(self,kind,name=None):
        a=['get',kind]
        if name:a.append(name)
        else:a+=['-l',LABEL+'='+self.state['run']]
        return json.loads(self.kubectl(*a,'-o','json').stdout)
    def guard(self,namespace=True):
        require(not RUNTIME.is_symlink() and stat.S_IMODE(RUNTIME.stat().st_mode)==0o700,'PRIVATE_RUNTIME_REQUIRED')
        s=self.load();k=RUNTIME/'kubeconfig'
        require(k.is_file() and not k.is_symlink() and stat.S_IMODE(k.stat().st_mode)==0o600,'PRIVATE_KUBECONFIG_REQUIRED')
        cfg=yaml.safe_load(k.read_text());require(len(cfg.get('clusters',[]))==len(cfg.get('contexts',[]))==len(cfg.get('users',[]))==1,'FOREIGN_KUBECONFIG')
        context='kind-'+s['name'];require(cfg.get('current-context')==context and cfg['contexts'][0]['name']==context,'FOREIGN_CONTEXT')
        require(re.fullmatch(r'https://127\.0\.0\.1:\d+',cfg['clusters'][0]['cluster']['server']) is not None,'NONLOOPBACK_APISERVER')
        require(not any(x in cfg['users'][0]['user'] for x in ('exec','auth-provider','tokenFile','client-key','client-certificate')),'EXTERNAL_AUTH_FORBIDDEN')
        node=json.loads(execute(['docker','inspect',s['name']+'-control-plane']).stdout)[0]
        require(node['Id']==s.get('node_id') and node['Config']['Labels'].get('io.x-k8s.kind.cluster')==s['name'],'NODE_OWNERSHIP_MISMATCH')
        if namespace:
            ns=self.get('namespace',s['namespace']);require(ns['metadata']['uid']==s.get('namespace_uid') and ns['metadata'].get('labels',{}).get(LABEL)==s['run'],'NAMESPACE_OWNERSHIP_MISMATCH')
        return s
    def own(self,kind,name):
        self.guard();obj=self.get(kind,name);uid=obj['metadata']['uid'];key=kind+'/'+name
        require(obj['metadata'].get('labels',{}).get(LABEL)==self.state['run'],'RESOURCE_LABEL_MISMATCH')
        if key in self.state['uids']:require(uid==self.state['uids'][key],'RESOURCE_UID_CHANGED')
        else:self.state['uids'][key]=uid;self.save()
        return obj
    def pods(self):return self.get('pods')['items']
    def api_pods(self):return [p for p in self.pods() if p['metadata']['labels'].get('app')=='orders' and not p['metadata'].get('deletionTimestamp')]
    def exec_java(self,pod,clazz,*args,allow_failure=False):
        self.own('pod',pod)
        return self.kubectl('exec',pod,'--','java','-Xmx64m','-cp','/opt/app/classes','labs.'+clazz,*args,allow_failure=allow_failure)
    def call(self,path='/info',method='GET',pod='caller',host='orders',allow_failure=False):
        r=self.exec_java(pod,'HttpCaller',f'http://{host}:8080{path}',method,allow_failure=allow_failure)
        try:value=json.loads(r.stdout.strip())
        except ValueError:raise LabError('INVALID_ENV','HTTP_TRANSPORT_NO_WITNESS')
        require('status' in value,'HTTP_TRANSPORT_NO_WITNESS');return value
    def eventually(self,fn,seconds=90,reason='OBSERVATION_TIMEOUT'):
        end=time.monotonic()+seconds
        while time.monotonic()<end:
            if fn():return
            time.sleep(1)
        raise LabError('FAIL',reason)
    def rollout(self):
        r=self.kubectl('rollout','status','deployment/orders','--timeout=120s',timeout=130,allow_failure=True)
        require(r.returncode==0,'ROLLOUT_NOT_READY','FAIL')
    def wait_startup(self,pod,seconds=90):
        deadline=time.monotonic()+seconds;saw_http=False;saw_503=False
        while time.monotonic()<deadline:
            try:
                response=self.call('/startup',pod=pod,host='127.0.0.1',allow_failure=True)
                saw_http=True;saw_503=saw_503 or response['status']==503
                if response['status']==200:return {'startup_http_503_observed':saw_503}
            except LabError as e:
                # Pod进入Running到JVM监听之间的短窗口可以重试，但没有HTTP绝不算业务负例。
                if e.reason!='HTTP_TRANSPORT_NO_WITNESS':raise
            time.sleep(1)
        raise LabError('FAIL' if saw_http else 'INVALID_ENV','STARTUP_NOT_COMPLETE' if saw_http else 'STARTUP_HTTP_UNAVAILABLE')
    def up(self,versions,task,task_dir):
        require(not RUNTIME.is_symlink(),'RUNTIME_SYMLINK_FORBIDDEN')
        require(not self.statefile.exists(),'EXISTING_RUN_USE_DOWN_FIRST');preflight(versions)
        RUNTIME.mkdir(mode=0o700,exist_ok=True);RUNTIME.chmod(0o700)
        run=secrets.token_hex(6);name='c11-kind-'+run
        clusters=execute(['kind','get','clusters']).stdout.splitlines();require(name not in clusters,'CLUSTER_NAME_COLLISION')
        self.state={'run':run,'name':name,'namespace':name,'phase':'PREPARING','uids':{},'images':{},'versions':versions,'task':task}
        self.save()
        stage=RUNTIME/'project';shutil.copytree(ROOT,stage,ignore=shutil.ignore_patterns('.runtime','__pycache__','build'))
        if task_dir:
            for source,target in TASKS[task].items():
                p=pathlib.Path(task_dir)/source;require(p.is_file() and not p.is_symlink(),'MISSING_TASK_FILE');shutil.copy2(p,stage/target)
        for release in ('v1','v2','broken'):
            tag=image_tag(run,release)
            execute(['docker','build','--build-arg','JAVA_BUILD_IMAGE='+versions['JAVA_BUILD_IMAGE'],'--build-arg','JAVA_RUNTIME_IMAGE='+versions['JAVA_RUNTIME_IMAGE'],'--build-arg','RELEASE='+release,'--tag',tag,str(stage)],timeout=600)
            self.state['images'][release]=tag;self.save()
        execute(['docker','pull',versions['REDIS_IMAGE']],timeout=180)
        redis_id=execute(['docker','image','inspect',versions['REDIS_IMAGE'],'--format','{{.Id}}']).stdout.strip()
        self.state['redis_local_id']=redis_id;self.save()
        config={'kind':'Cluster','apiVersion':'kind.x-k8s.io/v1alpha4','networking':{'apiServerAddress':'127.0.0.1'},'nodes':[{'role':'control-plane'}]}
        dump(RUNTIME/'kind-config.json',config)
        self.state['phase']='CREATING';self.save()
        execute(['kind','create','cluster','--name',name,'--image',versions['KIND_NODE_IMAGE'],'--config',str(RUNTIME/'kind-config.json'),'--kubeconfig',str(RUNTIME/'kubeconfig'),'--wait','120s'],timeout=180,env={**os.environ,'KUBECONFIG':str(RUNTIME/'kubeconfig')})
        (RUNTIME/'kubeconfig').chmod(0o600)
        node=json.loads(execute(['docker','inspect',name+'-control-plane']).stdout)[0];self.state['node_id']=node['Id'];self.save();self.guard(namespace=False)
        server=json.loads(self.kubectl('version','-o','json').stdout)
        require(server.get('serverVersion',{}).get('gitVersion')==versions['KUBERNETES_VERSION'],'SERVER_VERSION_MISMATCH')
        for image in [*self.state['images'].values(),versions['REDIS_IMAGE']]:execute(['kind','load','docker-image',image,'--name',name],timeout=180)
        ns={'apiVersion':'v1','kind':'Namespace','metadata':{'name':name,'labels':{LABEL:run,'pod-security.kubernetes.io/enforce':'restricted','pod-security.kubernetes.io/enforce-version':'v1.36'}}}
        self.kubectl('create','-f','-',input=json.dumps(ns));self.state['namespace_uid']=self.get('namespace',name)['metadata']['uid'];self.save()
        secret=secrets.token_urlsafe(32)
        sec={'apiVersion':'v1','kind':'Secret','metadata':{'name':'redis-auth','namespace':name,'labels':{LABEL:run}},'type':'Opaque','stringData':{'password':secret,'redis.conf':'bind 0.0.0.0\nport 6379\nprotected-mode yes\nrequirepass '+secret+'\nappendonly no\nsave ""\nmaxmemory 64mb\nmaxmemory-policy noeviction\ndir /data\n'}}
        self.kubectl('create','-f','-',input=json.dumps(sec));secret=None;sec=None
        self.own('secret','redis-auth')
        replacements={'${APP_IMAGE}':self.state['images']['v1'],'${REDIS_IMAGE}':versions['REDIS_IMAGE'],'${NAMESPACE}':name}
        docs=[]
        for f in ('rbac.yaml','config.yaml','redis.yaml','service.yaml','deployment.yaml','caller.yaml'):
            text=(stage/'manifests'/f).read_text()
            for a,b in replacements.items():text=text.replace(a,b)
            docs.extend(yaml.safe_load_all(text))
        docs=safe_documents(docs,name,run,set(self.state['images'].values())|{versions['REDIS_IMAGE']})
        self.guard();self.kubectl('apply','-f','-',input=json.dumps({'apiVersion':'v1','kind':'List','items':docs}))
        for obj in docs:self.own(obj['kind'].lower(),obj['metadata']['name'])
        self.kubectl('rollout','status','deployment/redis','--timeout=90s',timeout=100)
        self.kubectl('wait','pod/caller','--for=condition=Ready','--timeout=90s',timeout=100)
        self.eventually(lambda:len(self.api_pods())==2,reason='API_PODS_NOT_CREATED')
        # ready依赖seed，不能等待Service ready再seed；从各Pod localhost走bootstrap路径。
        for pod in self.api_pods():
            pname=pod['metadata']['name']
            self.kubectl('wait','pod/'+pname,'--for=jsonpath={.status.phase}=Running','--timeout=90s',timeout=100)
            evidence=self.wait_startup(pname)
            self.state.setdefault('bootstrap',[]).append({'pod_uid':pod['metadata']['uid'],**evidence});self.save()
            require(self.call('/seed','POST',pod=pname,host='127.0.0.1')['status']==200,'SEED_FAILED','FAIL')
        self.rollout();self.state['phase']='READY';self.save()
        return {'status':'READY','task':task,'run':run,'cluster':name,'namespace':name}
    def observe(self):
        self.guard();dep=self.own('deployment','orders')
        return {'status':'OBSERVED','deployment':{'generation':dep['metadata']['generation'],'available':dep.get('status',{}).get('availableReplicas',0),'updated':dep.get('status',{}).get('updatedReplicas',0)},'pods':[{'name':p['metadata']['name'],'uid':p['metadata']['uid'],'phase':p.get('status',{}).get('phase'),'ready':bool(p.get('status',{}).get('containerStatuses')) and all(c.get('ready',False) for c in p.get('status',{}).get('containerStatuses',[])),'restarts':sum(c.get('restartCount',0) for c in p.get('status',{}).get('containerStatuses',[]))} for p in self.api_pods()]}
    def pod_demo(self):
        self.guard();name='solo-orders'
        # 每次都新建；不接管已经存在的同名Pod。
        require(not any(p['metadata']['name']==name for p in self.pods()),'SOLO_POD_ALREADY_EXISTS')
        obj=yaml.safe_load((ROOT/'manifests/pod-example.yaml').read_text().replace('${APP_IMAGE}',self.state['images']['v1']))
        obj=safe_documents([obj],self.state['namespace'],self.state['run'],set(self.state['images'].values()))[0]
        self.state['uids'].pop('pod/'+name,None);self.save()
        self.kubectl('create','-f','-',input=json.dumps(obj));self.own('pod',name)
        uid=self.state['uids']['pod/'+name]
        try:
            self.kubectl('wait','pod/'+name,'--for=condition=Ready','--timeout=90s',timeout=100)
            require(self.call('/info',pod=name,host='127.0.0.1')['status']==200,'SOLO_POD_HTTP_FAILED','FAIL')
            require(not self.get('pod',name)['metadata'].get('ownerReferences'),'SOLO_POD_HAS_CONTROLLER','FAIL')
        finally:
            self.own('pod',name);self.kubectl('delete','pod',name,'--wait=true','--timeout=30s',timeout=40)
        time.sleep(5)
        require(not any(p['metadata']['name']==name for p in self.pods()),'SOLO_POD_RECREATED','FAIL')
        return {'status':'PASS','case':'standalone-pod','deleted_uid':uid,'observation_seconds':5,'evidence':'Standalone Pod served HTTP, had no controller owner, then stayed absent after deletion'}
    def down(self):
        self.guard();name=self.state['name']
        # 只删除node_id和namespace_uid双重核验过的独立课程集群；不删镜像、不prune。
        execute(['kind','delete','cluster','--name',name,'--kubeconfig',str(RUNTIME/'kubeconfig')],timeout=120)
        require(name not in execute(['kind','get','clusters']).stdout.splitlines(),'CLUSTER_DELETE_INCOMPLETE')
        shutil.rmtree(RUNTIME);return {'status':'REMOVED','cluster':name,'images':'RETAINED_FOR_REUSE'}
    def port_forward(self):
        self.own('service','orders')
        # 不写日志；只转发localhost。Ctrl+C停止，不改变context。
        args=['kubectl','--kubeconfig',str(RUNTIME/'kubeconfig'),'--context','kind-'+self.state['name'],'--namespace',self.state['namespace'],'port-forward','--address','127.0.0.1','service/orders','18080:8080']
        return subprocess.run(args).returncode

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('command',choices=['preflight','up','observe','pod-demo','call','verify','down','open']);p.add_argument('--versions');p.add_argument('--task',choices=TASKS,default='C11-04');p.add_argument('--task-dir');p.add_argument('--scenario',choices=['all','probes','config','rollout','resources'],default='all');args=p.parse_args()
    try:
        lab=Lab()
        if args.command in ('up','preflight'):
            require(bool(args.versions),'VERSION_LEDGER_REQUIRED');v=read_versions(args.versions)
            result=lab.up(v,args.task,args.task_dir) if args.command=='up' else (preflight(v) or {'status':'VALID_ENV'})
        elif args.command=='observe':result=lab.observe()
        elif args.command=='pod-demo':result=lab.pod_demo()
        elif args.command=='call':lab.guard();result=lab.call()
        elif args.command=='down':result=lab.down()
        elif args.command=='open':return lab.port_forward()
        else:
            from scenarios import verify
            lab.guard();result=verify(lab,args.scenario)
        print(json.dumps(result,ensure_ascii=False));return 0
    except LabError as e:print(json.dumps({'status':e.status,'reason':e.reason}));return 2 if e.status=='INVALID_ENV' else 1
    except (OSError,ValueError,KeyError,TypeError,yaml.YAMLError):print('{"status":"INVALID_ENV","reason":"MALFORMED_INPUT_OR_STATE"}');return 2
if __name__=='__main__':sys.exit(main())
